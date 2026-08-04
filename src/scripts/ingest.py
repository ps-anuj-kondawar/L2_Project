import sys
from chromadb import PersistentClient
from src.core.constants import CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME, RAG_DATA_PATH
from src.core.logger import logger


def main():
    logger.info("=== Lab Safety Auditor - RAG Ingestion ===")

    reset_db = "--reset" in sys.argv

    logger.info(f"Reading regulatory data from: {RAG_DATA_PATH}")
    with open(RAG_DATA_PATH, "r", encoding="utf-8") as f:
        raw_text = f.read()

    chunks = [chunk.strip() for chunk in raw_text.split("\n\n") if chunk.strip()]
    logger.info(f"  -> {len(chunks)} semantic chunks created")

    ids = [f"chunk_{i}" for i in range(len(chunks))]

    logger.info(f"Initialising ChromaDB at: {CHROMA_PERSIST_DIR}")
    client = PersistentClient(path=CHROMA_PERSIST_DIR)

    if reset_db:
        try:
            client.delete_collection(name=CHROMA_COLLECTION_NAME)
            logger.info(f"Deleted existing ChromaDB collection '{CHROMA_COLLECTION_NAME}' for reset.")
        except Exception as e:
            logger.warning(f"Could not delete collection for reset: {e}")

    collection = client.get_or_create_collection(name=CHROMA_COLLECTION_NAME)
    collection.upsert(documents=chunks, ids=ids)

    logger.info(f"[OK] Ingested {len(chunks)} chunks into ChromaDB collection '{CHROMA_COLLECTION_NAME}'")


if __name__ == "__main__":
    main()
