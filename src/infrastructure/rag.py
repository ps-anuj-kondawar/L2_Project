from chromadb import PersistentClient
from src.core.constants import CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME, RAG_TOP_K
from src.infrastructure.cache import get_osha_limits
from src.core.logger import logger

_client = None
_collection = None


def _get_collection():
    """Lazy-initialize ChromaDB client and collection on first use."""
    global _client, _collection
    if _collection is None:
        _client = PersistentClient(path=CHROMA_PERSIST_DIR)
        _collection = _client.get_or_create_collection(name=CHROMA_COLLECTION_NAME)
        try:
            if _collection.count() == 0:
                logger.warning("[RAG] ChromaDB collection is empty. Run 'python -m src.scripts.ingest' to populate regulatory data.")
        except Exception:
            pass
    return _collection


def query_regulations(chemical_name: str) -> list[str]:
    cached = get_osha_limits(chemical_name)
    if cached:
        parts = []
        if "ppm" in cached:
            parts.append(f"{cached['ppm']} ppm TWA")
        if "pct" in cached:
            parts.append(f"{cached['pct']}% by volume")
        parts.append(f"Source: {cached.get('citation', 'SQLite cache')}")
        return [f"{chemical_name}: " + ", ".join(parts)]

    try:
        results = _get_collection().query(
            query_texts=[chemical_name],
            n_results=RAG_TOP_K
        )
        return results["documents"][0]
    except Exception:
        return []
