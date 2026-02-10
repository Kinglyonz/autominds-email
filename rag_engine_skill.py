"""
RAG Engine Skill for AutoMinds Intelligence (AMI)
Handles the core Retrieval-Augmented Generation (RAG) pipeline.

Uses scikit-learn TF-IDF for lightweight, reliable vector search.
No GPU needed. No heavy frameworks. Works everywhere.

- Processes documents (PDFs, text)
- Splits documents into chunks
- Creates TF-IDF vectors for similarity search
- Queries the index to find relevant context for a given question
"""

import json
import logging
import os
import io
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Persistent storage for each user's knowledge base
KNOWLEDGE_DIR = Path("knowledge_stores")
KNOWLEDGE_DIR.mkdir(exist_ok=True)


def _get_store_path(user_id: str) -> Path:
    """Path to a user's knowledge store."""
    return KNOWLEDGE_DIR / f"{user_id}_chunks.json"


def _extract_text_from_pdf(file_content: io.BytesIO) -> str:
    """Extract text from a PDF file stream."""
    try:
        reader = PdfReader(file_content)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
        return ""


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks


def process_and_store_documents(documents: list[tuple[str, io.BytesIO]], user_id: str):
    """
    Processes a list of documents and saves text chunks to disk.
    `documents` is a list of (file_name, file_content_stream).
    """
    all_chunks = []

    for file_name, file_content in documents:
        if file_name.lower().endswith(".pdf"):
            text = _extract_text_from_pdf(file_content)
        else:
            try:
                text = file_content.read().decode("utf-8", errors="ignore")
            except Exception:
                logger.warning(f"Could not read {file_name}, skipping.")
                continue

        if not text.strip():
            logger.warning(f"No text extracted from {file_name}, skipping.")
            continue

        chunks = _chunk_text(text)
        for chunk in chunks:
            all_chunks.append({
                "source": file_name,
                "content": chunk,
            })

    if not all_chunks:
        logger.info("No processable documents found.")
        return

    store_path = _get_store_path(user_id)

    # Merge with existing chunks if store exists
    existing_chunks = []
    if store_path.exists():
        try:
            existing_chunks = json.loads(store_path.read_text(encoding="utf-8"))
        except Exception:
            existing_chunks = []

    # Avoid duplicates by checking source + first 100 chars
    existing_keys = {(c["source"], c["content"][:100]) for c in existing_chunks}
    new_chunks = [c for c in all_chunks if (c["source"], c["content"][:100]) not in existing_keys]

    combined = existing_chunks + new_chunks
    store_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"Stored {len(new_chunks)} new chunks for user {user_id} (total: {len(combined)}).")


def query_knowledge_base(query: str, user_id: str, top_k: int = 4) -> str:
    """
    Queries the user's knowledge base using TF-IDF cosine similarity.
    Returns the most relevant text chunks as context.
    """
    store_path = _get_store_path(user_id)
    if not store_path.exists():
        return "No knowledge base found for this user. Please sync your documents first."

    try:
        chunks = json.loads(store_path.read_text(encoding="utf-8"))
    except Exception:
        return "Error reading knowledge base."

    if not chunks:
        return "Knowledge base is empty."

    # Build TF-IDF matrix from all chunks + the query
    texts = [c["content"] for c in chunks]
    texts.append(query)

    vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
    tfidf_matrix = vectorizer.fit_transform(texts)

    # Compare query (last vector) against all chunk vectors
    query_vec = tfidf_matrix[-1]
    chunk_vecs = tfidf_matrix[:-1]
    similarities = cosine_similarity(query_vec, chunk_vecs).flatten()

    # Get top-k most similar chunks
    top_indices = similarities.argsort()[-top_k:][::-1]
    top_chunks = [chunks[i] for i in top_indices if similarities[i] > 0.05]

    if not top_chunks:
        return "I could not find any relevant information in your knowledge base."

    # Format context with source attribution
    context_parts = []
    for chunk in top_chunks:
        context_parts.append(f"[Source: {chunk['source']}]\n{chunk['content']}")

    return "\n\n---\n\n".join(context_parts)
