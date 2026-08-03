from chromadb import PersistentClient
from src.core.constants import CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME, RAG_DATA_PATH


def main():
    print("=== Lab Safety Auditor - RAG Ingestion ===")

    print(f"Reading regulatory data from: {RAG_DATA_PATH}")
    with open(RAG_DATA_PATH, "r", encoding="utf-8") as f:
        raw_text = f.read()

    chunks = [chunk.strip() for chunk in raw_text.split("\n\n") if chunk.strip()]
    print(f"  -> {len(chunks)} semantic chunks created")

    ids = [f"chunk_{i}" for i in range(len(chunks))]

    print(f"Initialising ChromaDB at: {CHROMA_PERSIST_DIR}")
    client = PersistentClient(path=CHROMA_PERSIST_DIR)
    collection = client.get_or_create_collection(name=CHROMA_COLLECTION_NAME)
    collection.add(documents=chunks, ids=ids)

    print(f"\n[OK] Ingested {len(chunks)} chunks into ChromaDB collection '{CHROMA_COLLECTION_NAME}'")


if __name__ == "__main__":
    main()
