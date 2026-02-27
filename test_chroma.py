import chromadb
from langchain_core.documents import Document

def test_chroma():
    print("Testing ChromaDB...")
    client = chromadb.PersistentClient(path="./data/chroma_db")
    collection = client.get_or_create_collection(name="test_collection")
    collection.add(
        documents=["This is a dummy document about Patrick Mahomes."],
        metadatas=[{"source": "test"}],
        ids=["doc1"]
    )
    
    results = collection.query(
        query_texts=["Who is this document about?"],
        n_results=1
    )
    
    print("Query Results:", results['documents'])
    print("Test passed if Patrick Mahomes is mentioned above.")

if __name__ == "__main__":
    test_chroma()
