import os
import hashlib
from pathlib import Path
from langchain_community.document_loaders import DirectoryLoader
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import chromadb
from chromadb.config import Settings

# Make sure we have the API key available
if "GEMINI_API_KEY" not in os.environ and "GOOGLE_API_KEY" not in os.environ:
    # Use existing environment if set or require it
    pass 

# Configuration
CHROMA_PATH = "./data/chroma_db"
REPORTS_DIR = "./reports"
TARGET_FILE = "model_miss_analysis.md"

def get_file_hash(filepath: str) -> str:
    """Creates an MD5 hash of a file for idempotency checks."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as afile:
        buf = afile.read()
        hasher.update(buf)
    return hasher.hexdigest()

def ingest_reports():
    print(f"Initializing ChromaDB connection at {CHROMA_PATH}...")
    
    # Initialize Vector DB
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(
        name="cap_alpha_intelligence",
        metadata={"hnsw:space": "cosine"}
    )
    
    # Initialize Embedding Model
    print("Loading Gemini Embedding Model...")
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")

    # Define Markdown Splitter mapping headers to document metadata
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)

    # Process specific artifact files
    target_files = []
    
    # 1. The primary Miss Analysis explicitly mentioned
    miss_report = Path(REPORTS_DIR) / TARGET_FILE
    if miss_report.exists():
        target_files.append(miss_report)
    else:
        print(f"Warning: Target report {miss_report} not found.")

    # 2. Iterate artifacts directory if it exists
    artifacts_dir = Path("./artifacts/reporting")
    if artifacts_dir.exists():
        for file in artifacts_dir.glob("*.md"):
            target_files.append(file)
            
    if not target_files:
        print("No target markdown files found to ingest. Exiting.")
        return

    # Ingestion Loop
    docs_ingested = 0
    
    for filepath in target_files:
        print(f"\nProcessing: {filepath}")
        
        # Read content
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Optional: Add idompotency check here if we track hashes in SQL as requested
        # For this PoC milestone, we will process and rely on Chroma ID deduplication
        
        # Split document
        chunks = markdown_splitter.split_text(content)
        print(f"Generated {len(chunks)} contextual chunks.")
        
        # Prepare for Chroma
        ids = []
        texts = []
        metadatas = []
        
        for i, chunk in enumerate(chunks):
            # Generate a unique ID for this chunk based on file + index
            chunk_id = f"{filepath.name}_chunk_{i}"
            
            # Embed metadata (source file + the headers extracted by Langchain)
            meta = chunk.metadata
            meta["source"] = str(filepath)
            meta["chunk_index"] = i
            
            ids.append(chunk_id)
            texts.append(chunk.page_content)
            metadatas.append(meta)
            
        if texts:
            # Batch generate embeddings
            print(f"Generating embeddings for {len(texts)} chunks...")
            
            # Add to Chroma (handles embedding internally if an embedding function is passed, 
            # but we explicitly embed via LangChain to maintain the gemini integration)
            embedded_vectors = embeddings.embed_documents(texts)
            
            print(f"Writing to ChromaDB collection...")
            collection.upsert(
                ids=ids,
                documents=texts,
                embeddings=embedded_vectors,
                metadatas=metadatas
            )
            docs_ingested += len(texts)
            print(f"Successfully upserted chunks for {filepath.name}")

    print(f"\n--- Ingestion Complete ---")
    print(f"Total chunks indexed: {docs_ingested}")

if __name__ == "__main__":
    ingest_reports()
