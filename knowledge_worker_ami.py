"""
Knowledge Worker AMI (AutoMinds Intelligence)
The first AMI agent — provides RAG-powered knowledge base capabilities.

Following the uncle's blueprint:
  Skills → Agent → Marketplace

This agent orchestrates:
  - google_drive_skill: To fetch documents from user's Google Drive
  - rag_engine_skill: To index documents and query the knowledge base

It exposes a clean interface for the server to call.
"""

import logging
from datetime import datetime
from anthropic import Anthropic

import google_drive_skill
import rag_engine_skill
import user_store
from config import settings

logger = logging.getLogger("ami.knowledge-worker")

client = Anthropic(api_key=settings.anthropic_api_key)


def sync_user_drive_folder(user_id: str, folder_id: str) -> dict:
    """
    Syncs a user's Google Drive folder into their personal RAG knowledge base.
    
    Steps (following the skill pattern):
    1. Use google_drive_skill to list files in the folder
    2. Use google_drive_skill to download each file
    3. Use rag_engine_skill to process and store documents
    """
    user = user_store.get_user(user_id)
    if not user or not user.connected_accounts:
        return {"success": False, "error": "User not found or no connected Google account."}

    # Find the Google account
    google_account = None
    for account in user.connected_accounts:
        if account.provider == "google":
            google_account = account
            break

    if not google_account:
        return {"success": False, "error": "No Google account connected."}

    try:
        # Skill 1: List files in the Drive folder
        files = google_drive_skill.list_files_in_folder(google_account, folder_id)

        if not files:
            return {"success": True, "message": "No files found in the specified folder.", "files_processed": 0}

        # Skill 2: Download each file
        documents = []
        skipped = []
        for f in files:
            mime = f.get("mimeType", "")
            name = f.get("name", "unknown")

            # Only process supported file types for now
            if name.lower().endswith(".pdf") or "pdf" in mime:
                try:
                    content = google_drive_skill.download_file(google_account, f["id"])
                    documents.append((name, content))
                except Exception as e:
                    logger.warning(f"Failed to download {name}: {e}")
                    skipped.append(name)
            else:
                skipped.append(name)

        if not documents:
            return {
                "success": True,
                "message": "No supported documents found (PDF only for now).",
                "files_processed": 0,
                "skipped": skipped,
            }

        # Skill 3: Process and store in RAG engine
        rag_engine_skill.process_and_store_documents(documents, user_id)

        logger.info(f"Knowledge sync complete for user {user_id}: {len(documents)} files indexed.")

        return {
            "success": True,
            "message": f"Successfully indexed {len(documents)} document(s) into your knowledge base.",
            "files_processed": len(documents),
            "files_indexed": [d[0] for d in documents],
            "skipped": skipped,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Knowledge sync failed for user {user_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def ask_knowledge_base(user_id: str, question: str, persona: str | None = None) -> dict:
    """
    Ask a question to the user's personal knowledge base.
    
    This is the core RAG flow:
    1. Use rag_engine_skill to find relevant context from the user's indexed documents
    2. Send that context + the question to Claude to generate a grounded answer

    If a `persona` is provided, the AI will respond in that persona's voice and style.
    This is how we create "Digital Clones" (e.g., Digital Jeremiah).
    """
    try:
        # Skill: Query the RAG engine for relevant context
        context = rag_engine_skill.query_knowledge_base(question, user_id)

        if "No knowledge base found" in context:
            return {
                "success": False,
                "answer": context,
                "source": "system",
            }

        # Build the system prompt
        if persona:
            system_prompt = f"""You are {persona}. You are a digital clone of a real person.
Your purpose is to answer questions and provide guidance based ONLY on the knowledge 
and teachings found in the provided context. Adopt their voice, style, and personality.

If the answer is not in the context, say so honestly. Do not make up information.
Always stay true to the person's known principles and beliefs.

Context from knowledge base:
{context}"""
        else:
            system_prompt = f"""You are an AMI (AutoMinds Intelligence) Knowledge Worker.
Your job is to answer the user's question based ONLY on the information found in their
personal knowledge base. Be helpful, accurate, and cite which document the information
came from when possible.

If the answer is not in the provided context, say "I couldn't find that in your knowledge base."

Context from knowledge base:
{context}"""

        # Call Claude with the grounded context
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": question}],
            system=system_prompt,
        )

        answer = response.content[0].text

        return {
            "success": True,
            "answer": answer,
            "source": "knowledge_base",
            "persona": persona or "Knowledge Worker",
            "model": settings.claude_model,
        }

    except Exception as e:
        logger.error(f"Knowledge query failed for user {user_id}: {e}", exc_info=True)
        return {"success": False, "answer": f"Error: {str(e)}", "source": "error"}
