"""
RAG Engine Skill for AutoMinds Intelligence (AMI)
Handles the core Retrieval-Augmented Generation (RAG) pipeline.

- Processes documents (PDFs, text)
- Splits documents into chunks
- Creates vector embeddings using an AI model
- Stores embeddings in a FAISS vector store
- Queries the vector store to find relevant context for a given question
"""

import logging
import os
from pathlib import Path
import io

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyPDFLoader
from langchain_anthropic import AnthropicEmbeddings
from langchain.docstore.document import Document

from config import settings

logger = logging.getLogger(__name__)

# Define a persistent path for vector stores for each user
VECTOR_STORE_DIR = Path("vector_stores")
VECTOR_STORE_DIR.mkdir(exist_ok=True)

# Initialize the embedding model once to be reused
# This uses the Anthropic API to convert text into numerical vectors.
try:
    embeddings = AnthropicEmbeddings(model="claude-3-sonnet-20240229", api_key=settings.anthropic_api_key)
except Exception as e:
    logger.error(f"Failed to initialize AnthropicEmbeddings: {e}")
    embeddings = None

def _get_vector_store_path(user_id: str) -> str:
    """Generates a unique path for a user's specific vector store."""
    return str(VECTOR_STORE_DIR / f"{user_id}_faiss_index")

def _load_documents_from_pdf(file_content: io.BytesIO, file_name: str) -> list[Document]:
    """Loads text from a PDF file stream."""
    # PyPDFLoader needs a file path, so we temporarily save the stream to disk.
    temp_pdf_path = f"temp_{file_name}"
    try:
        with open(temp_pdf_path, "wb") as f:
            f.write(file_content.read())
        
        loader = PyPDFLoader(temp_pdf_path)
        documents = loader.load()
        return documents
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

def process_and_store_documents(documents: list[tuple[str, io.BytesIO]], user_id: str):
    """
    Processes a list of documents and adds them to the user's vector store.
    `documents` is a list of (file_name, file_content_stream).
    """
    if not embeddings:
        raise RuntimeError("Embeddings model is not initialized.")

    all_docs = []
    for file_name, file_content in documents:
        if file_name.lower().endswith(".pdf"):
            docs = _load_documents_from_pdf(file_content, file_name)
            all_docs.extend(docs)
        # TODO: Add handlers for other file types like .txt, .docx here
        else:
            logger.warning(f"Unsupported file type: {file_name}. Skipping.")
            continue

    if not all_docs:
        logger.info("No processable documents found.")
        return

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(all_docs)

    vector_store_path = _get_vector_store_path(user_id)

    if os.path.exists(vector_store_path):
        # Load existing store and merge
        db = FAISS.load_local(vector_store_path, embeddings, allow_dangerous_deserialization=True)
        db.add_documents(splits)
    else:
        # Create a new store
        db = FAISS.from_documents(splits, embeddings)

    db.save_local(vector_store_path)
    logger.info(f"Successfully processed and stored {len(splits)} document chunks for user {user_id}.")


def query_knowledge_base(query: str, user_id: str) -> str:
    """
    Queries the user's knowledge base to find relevant context.
    Returns a string of the most relevant document chunks.
    """
    if not embeddings:
        raise RuntimeError("Embeddings model is not initialized.")

    vector_store_path = _get_vector_store_path(user_id)
    if not os.path.exists(vector_store_path):
        return "No knowledge base found for this user. Please sync your documents first."

    db = FAISS.load_local(vector_store_path, embeddings, allow_dangerous_deserialization=True)
    
    # Get the 4 most relevant document chunks
    docs = db.similarity_search(query, k=4)

    if not docs:
        return "I could not find any relevant information in your knowledge base to answer that question."

    # Combine the content of the relevant chunks into a single context string
    context = "\n\n".join([doc.page_content for doc in docs])
    return context
