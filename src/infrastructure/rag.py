from chromadb import PersistentClient
from src.core.constants import CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME, RAG_TOP_K
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


def query_regulations(chemical_name: str, region: str = "US") -> list[str]:
    """
    Query ChromaDB for regulatory text chunks related to the chemical.

    Always performs a real vector similarity search against the ChromaDB collection.
    Cache lookups are handled upstream in chemical_agent Layer 3 — this function
    must always return real RAG results so the rag_context_relevancy metric
    reflects genuine retrieval, not cache hits.

    Args:
        chemical_name: Name of the chemical to query for.
        region: Regulatory region code (e.g. 'US', 'EU').

    Returns:
        List of regulatory text chunk strings from ChromaDB. Empty list on failure.
    """
    try:
        results = _get_collection().query(
            query_texts=[f"{chemical_name} {region} regulations permissible exposure limit PEL TWA"],
            n_results=RAG_TOP_K
        )
        return results["documents"][0]
    except Exception:
        return []
