"""
ChemShield AI — Multi-Tier High-Performance SQLite Caching Layer.

Provides persistent, thread-safe caching across all pipeline sub-systems:
- Tier 1 (OSHA Limits Cache): Pre-computed regulatory exposure limits by chemical name
- Tier 2 (Semantic Input Cache): Deterministic hashing of user input formulations and intents
- Tier 3 (Summary Cache): Pre-generated single-sentence summaries keyed by violation fingerprint
- Tier 4 (Conversation Cache): Multi-turn Copilot query and dialogue response caching
- Tier 5 (PubChem Cache): Authoritative GHS hazard statements, CIDs, and CAS numbers

Thread Safety & Performance:
- Write-Ahead Logging (WAL) enabled on SQLite database initialization
- Thread-local connection pool (_local.conn) avoids multi-threaded SQLite lock contention
- Fail-open exception handling ensures pipeline resilience even if cache is unreachable
"""

import hashlib
import json
import os
import sqlite3
import threading
import time

from src.core.logger import logger

DB_PATH = ":memory:" if os.getenv("TESTING", "").lower() in ("true", "1") else os.getenv("CACHE_DB_PATH", "./cache.db")
CACHE_TTL = 60 * 60 * 24 * 30  # 30 days in seconds

_local = threading.local()


def _init_db() -> None:
    """
    Initialize SQLite schema and enable Write-Ahead Logging (WAL) mode.
    Executed once upon module import to create all caching tables if not present.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS osha_cache "
            "(chemical TEXT PRIMARY KEY, limits_json TEXT, created_at REAL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS summary_cache "
            "(violations_hash TEXT PRIMARY KEY, summary TEXT, created_at REAL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS input_cache "
            "(input_hash TEXT PRIMARY KEY, report_json TEXT, created_at REAL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS conversation_cache "
            "(query_hash TEXT PRIMARY KEY, response TEXT, created_at REAL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS pubchem_cache "
            "(chemical TEXT PRIMARY KEY, pubchem_json TEXT, created_at REAL)"
        )
        conn.commit()


_init_db()


def _get_conn() -> sqlite3.Connection:
    """
    Retrieve or create a thread-local SQLite connection.

    Ensures each thread reuses its own dedicated database connection,
    avoiding concurrent access violations while eliminating connection creation overhead.

    Returns:
        sqlite3.Connection: Active thread-bound database connection.
    """
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        _local.conn = conn
    return conn


def get_osha_limits(chemical: str) -> dict | None:
    """
    Retrieve cached OSHA regulatory exposure limits for a chemical.

    Args:
        chemical (str): Chemical name (case-insensitive lookup).

    Returns:
        dict | None: Cached limits dictionary if found and unexpired; None otherwise.
    """
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT limits_json, created_at FROM osha_cache WHERE chemical = ?",
            (chemical.lower().strip(),)
        ).fetchone()
        if row and (time.time() - row[1]) < CACHE_TTL:
            return json.loads(row[0])
    except Exception as e:
        logger.warning(f"[Cache] get_osha_limits failed for '{chemical}': {e}")
    return None


def set_osha_limits(chemical: str, limits: dict) -> None:
    """
    Store OSHA regulatory exposure limits for a chemical in the persistent cache.

    Args:
        chemical (str): Chemical name key.
        limits (dict): Regulatory limits dictionary to serialize.
    """
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO osha_cache VALUES (?, ?, ?)",
                (chemical.lower().strip(), json.dumps(limits), time.time())
            )
    except Exception as e:
        logger.warning(f"[Cache] set_osha_limits failed for '{chemical}': {e}")


# ── LAYER 2: Exact Input Cache (using SQLite for precision safety) ─────────

def get_semantic_cache(input_text: str, intent: str = "audit", region: str = "US", language: str = "en") -> dict | None:
    """
    Retrieve a previously computed full audit report for an identical input formulation.

    Args:
        input_text (str): Lab formulation input string.
        intent (str): Execution intent.
        region (str): Regulatory region code.
        language (str): Target language.

    Returns:
        dict | None: Deserialized compliance report payload, or None on cache miss.
    """
    try:
        key_str = f"{input_text.strip()}|intent={intent}|region={region}|lang={language}"
        h = hashlib.sha256(key_str.encode()).hexdigest()
        conn = _get_conn()
        row = conn.execute(
            "SELECT report_json, created_at FROM input_cache WHERE input_hash = ?", (h,)
        ).fetchone()
        if row and (time.time() - row[1]) < CACHE_TTL:
            return json.loads(row[0])
    except Exception as e:
        logger.warning(f"[Cache] get_semantic_cache failed: {e}")
    return None


def set_semantic_cache(input_text: str, report_json: str, intent: str = "audit", region: str = "US", language: str = "en") -> None:
    """
    Persist an audit run result under its composite input key hash.

    Args:
        input_text (str): Lab formulation input text.
        report_json (str): Serialized AgentRunResult or ComplianceReport JSON.
        intent (str): Execution intent.
        region (str): Target regulatory region.
        language (str): Target language.
    """
    try:
        key_str = f"{input_text.strip()}|intent={intent}|region={region}|lang={language}"
        h = hashlib.sha256(key_str.encode()).hexdigest()
        with _get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO input_cache VALUES (?, ?, ?)",
                (h, report_json, time.time())
            )
    except Exception as e:
        logger.warning(f"[Cache] set_semantic_cache failed: {e}")


# ── LAYER 3: LLM Summary SQLite cache ───────────────────────────────────────

def _hash_violations(violations: list[str]) -> str:
    """Compute a deterministic SHA-256 fingerprint for a sorted list of violation strings."""
    key = "|".join(sorted(violations))
    return hashlib.sha256(key.encode()).hexdigest()


def get_summary_cache(violations: list[str]) -> str | None:
    """
    Retrieve cached LLM synthesis summary for an identical set of hazard violations.

    Args:
        violations (list[str]): List of violation descriptions.

    Returns:
        str | None: Cached summary sentence, or None if not present.
    """
    try:
        h = _hash_violations(violations)
        conn = _get_conn()
        row = conn.execute(
            "SELECT summary, created_at FROM summary_cache WHERE violations_hash = ?", (h,)
        ).fetchone()
        if row and (time.time() - row[1]) < CACHE_TTL:
            return row[0]
    except Exception as e:
        logger.warning(f"[Cache] get_summary_cache failed: {e}")
    return None


def set_summary_cache(violations: list[str], summary: str) -> None:
    """
    Store an LLM synthesis summary keyed by the violation fingerprint.

    Args:
        violations (list[str]): List of violation descriptions.
        summary (str): Generated single-sentence summary string.
    """
    try:
        h = _hash_violations(violations)
        with _get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO summary_cache VALUES (?, ?, ?)",
                (h, summary, time.time())
            )
    except Exception as e:
        logger.warning(f"[Cache] set_summary_cache failed: {e}")


def get_conversation_cache(message: str, history: list) -> str | None:
    """
    Look up cached Copilot response for an identical prompt and history state.

    Args:
        message (str): Current user prompt.
        history (list): Conversation history turns.

    Returns:
        str | None: Cached response text or None.
    """
    try:
        history_str = json.dumps(history)
        key = f"{history_str}|||{message.strip()}"
        h = hashlib.sha256(key.encode()).hexdigest()
        
        conn = _get_conn()
        row = conn.execute(
            "SELECT response, created_at FROM conversation_cache WHERE query_hash = ?", (h,)
        ).fetchone()
        if row and (time.time() - row[1]) < CACHE_TTL:
            return row[0]
    except Exception as e:
        logger.warning(f"[Cache] get_conversation_cache failed: {e}")
    return None


def set_conversation_cache(message: str, history: list, response: str) -> None:
    """
    Persist Copilot response keyed by composite message and history hash.

    Args:
        message (str): Current user prompt.
        history (list): Conversation history turns.
        response (str): LLM response text.
    """
    try:
        history_str = json.dumps(history)
        key = f"{history_str}|||{message.strip()}"
        h = hashlib.sha256(key.encode()).hexdigest()
        
        with _get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO conversation_cache VALUES (?, ?, ?)",
                (h, response, time.time())
            )
    except Exception as e:
        logger.warning(f"[Cache] set_conversation_cache failed: {e}")


def get_pubchem_cache(chemical: str) -> dict | None:
    """
    Retrieve cached PubChem GHS classification and property metadata.

    Args:
        chemical (str): Chemical name.

    Returns:
        dict | None: Cached PubChem metadata dictionary (7-day TTL).
    """
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT pubchem_json, created_at FROM pubchem_cache WHERE chemical = ?",
            (chemical.lower().strip(),)
        ).fetchone()
        # 7-day TTL for PubChem cache
        if row and (time.time() - row[1]) < (60 * 60 * 24 * 7):
            return json.loads(row[0])
    except Exception as e:
        logger.warning(f"[Cache] get_pubchem_cache failed for '{chemical}': {e}")
    return None


def set_pubchem_cache(chemical: str, data: dict) -> None:
    """
    Store PubChem GHS classification and property metadata in cache.

    Args:
        chemical (str): Chemical name key.
        data (dict): PubChem data dictionary.
    """
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pubchem_cache VALUES (?, ?, ?)",
                (chemical.lower().strip(), json.dumps(data), time.time())
            )
    except Exception as e:
        logger.warning(f"[Cache] set_pubchem_cache failed for '{chemical}': {e}")



