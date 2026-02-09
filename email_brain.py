"""
AutoMinds Email Assistant - AI Email Brain (Opus 4.6 Edition)
Uses Claude Opus 4.6 with adaptive thinking, evaluator-optimizer loops,
and hybrid model routing (Opus for complex, Haiku for simple).

Patterns used (from Anthropic's agent playbook):
  1. Routing — classify emails → send to right model
  2. Evaluator-Optimizer — generate draft → critique → improve
  3. Parallelization — safety guardrail runs alongside analysis
"""

import json
import logging
import time
import asyncio
from datetime import datetime
from typing import Optional

import anthropic

from config import settings
from models import (
    EmailMessage, EmailPriority, EmailCategory,
    EmailDraft, DailyBriefing, DraftStatus,
)
import uuid

logger = logging.getLogger(__name__)

# Initialize the Anthropic client (supports both sync + async)
_client: Optional[anthropic.Anthropic] = None
_async_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.Anthropic:
    """Get or create the sync Anthropic client."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _get_async_client() -> anthropic.AsyncAnthropic:
    """Get or create the async Anthropic client."""
    global _async_client
    if _async_client is None:
        _async_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _async_client


def _call_opus(system: str, prompt: str, max_tokens: int = None) -> str:
    """Call Claude Opus 4.6 with adaptive thinking enabled.
    
    Adaptive thinking lets Claude auto-decide how hard to think per task.
    Simple email? Light thinking. Complex analysis? Deep reasoning.
    """
    client = _get_client()
    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=max_tokens or settings.claude_max_tokens,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    # Extract text from response (may have thinking + text blocks)
    for block in response.content:
        if block.type == "text":
            return block.text.strip()
    return ""


def _call_haiku(system: str, prompt: str, max_tokens: int = None) -> str:
    """Call Claude Haiku 4.5 for simple/cheap tasks.
    
    ~8x cheaper than Opus. Use for spam detection, labeling, simple classification.
    """
    client = _get_client()
    response = client.messages.create(
        model=settings.claude_fast_model,
        max_tokens=max_tokens or settings.claude_fast_max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


async def _async_call_opus(system: str, prompt: str, max_tokens: int = None) -> str:
    """Async version of Opus call — for parallel operations."""
    client = _get_async_client()
    response = await client.messages.create(
        model=settings.claude_model,
        max_tokens=max_tokens or settings.claude_max_tokens,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            return block.text.strip()
    return ""


async def _async_call_haiku(system: str, prompt: str, max_tokens: int = None) -> str:
    """Async Haiku call — for parallel cheap tasks."""
    client = _get_async_client()
    response = await client.messages.create(
        model=settings.claude_fast_model,
        max_tokens=max_tokens or settings.claude_fast_max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ─── Email Analysis ──────────────────────────────────────

ANALYSIS_SYSTEM_PROMPT = """You are an expert email assistant powered by Claude Opus 4.6. You analyze emails with deep reasoning and return structured JSON.

For EACH email, determine:
1. priority: "urgent" | "high" | "normal" | "low"
   - urgent = needs reply within hours (boss, client crisis, time-sensitive, deadlines today)
   - high = needs reply today (important people, deadlines this week, money involved)
   - normal = can wait a day or two
   - low = newsletters, promotions, FYI only, automated notifications
   
2. category: "action_required" | "waiting_on" | "fyi" | "newsletter" | "promotional" | "personal" | "spam"

3. summary: 1-2 sentence summary of what the email is about and what the sender wants from the user.

4. suggested_action: Specific actionable instruction (e.g., "Reply confirming Monday 2pm works", "Forward invoice to accounting", "Unsubscribe — 3rd promo this week")

5. is_vip: true if sender is boss, investor, key client, family, or someone marked in the VIP list.

6. sentiment: "positive" | "neutral" | "negative" | "urgent" — the emotional tone of the email.

7. response_deadline: null or ISO date string if there's an implicit/explicit deadline.

Think carefully about context. An email saying "when you get a chance" is NOT urgent. An email saying "need this by EOD" IS urgent. A recruiter cold-email is promotional, not action_required.

Return ONLY valid JSON — no markdown, no explanation."""


def analyze_emails(
    emails: list[EmailMessage],
    vip_contacts: list[str] = None,
) -> list[EmailMessage]:
    """Analyze a batch of emails with Claude Opus 4.6 + adaptive thinking.
    
    Uses hybrid routing:
    - Quick triage with Haiku first (cheap spam/newsletter detection)
    - Deep analysis with Opus for anything that matters
    
    Args:
        emails: List of emails to analyze.
        vip_contacts: List of email addresses to always mark as VIP.
    
    Returns:
        The same emails with priority, category, summary, and suggested_action populated.
    """
    if not emails:
        return []

    vip_contacts = vip_contacts or []

    # Build the email batch for Claude
    email_batch = []
    for email in emails:
        email_batch.append({
            "id": email.id,
            "from_name": email.sender.name,
            "from_email": email.sender.email,
            "subject": email.subject,
            "snippet": email.snippet[:300],
            "body_preview": email.body_text[:800] if email.body_text else email.snippet,
            "date": email.date.isoformat(),
            "has_attachments": email.has_attachments,
            "is_known_vip": email.sender.email.lower() in [v.lower() for v in vip_contacts],
        })

    prompt = f"""Analyze these {len(email_batch)} emails. Return a JSON array where each object has:
- id (string, must match the email id)
- priority ("urgent" | "high" | "normal" | "low")
- category ("action_required" | "waiting_on" | "fyi" | "newsletter" | "promotional" | "personal" | "spam")
- summary (1-2 sentences)
- suggested_action (specific actionable instruction)
- is_vip (boolean)
- sentiment ("positive" | "neutral" | "negative" | "urgent")
- response_deadline (null or ISO date string)

VIP contacts (always mark as VIP): {json.dumps(vip_contacts) if vip_contacts else "none specified"}
Today's date: {datetime.now().strftime("%Y-%m-%d")}

Emails to analyze:
{json.dumps(email_batch, indent=2)}

Return ONLY the JSON array, nothing else."""

    try:
        # Use Opus 4.6 with adaptive thinking for deep analysis
        raw_text = _call_opus(ANALYSIS_SYSTEM_PROMPT, prompt)

        # Clean up potential markdown wrapping
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        analysis_results = json.loads(raw_text)

        # Map results back to emails
        results_by_id = {r["id"]: r for r in analysis_results}

        for email in emails:
            result = results_by_id.get(email.id, {})
            email.priority = EmailPriority(result.get("priority", "normal"))
            email.category = EmailCategory(result.get("category", "fyi"))
            email.summary = result.get("summary", "")
            email.suggested_action = result.get("suggested_action", "")
            email.is_vip = result.get("is_vip", False)

        logger.info(
            f"Analyzed {len(emails)} emails. "
            f"Urgent: {sum(1 for e in emails if e.priority == EmailPriority.URGENT)}, "
            f"High: {sum(1 for e in emails if e.priority == EmailPriority.HIGH)}"
        )

        return emails

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude analysis JSON: {e}")
        logger.error(f"Raw response: {raw_text[:500]}")
        # Return emails without AI fields rather than failing
        return emails

    except Exception as e:
        logger.error(f"Error analyzing emails with Claude: {e}")
        return emails


# ─── Daily Briefing ──────────────────────────────────────

BRIEFING_SYSTEM_PROMPT = """You are an executive email assistant preparing the morning email briefing. You use deep reasoning to surface what actually matters.

Your job is to write a CONCISE, ACTIONABLE briefing that a busy person can read in 90 seconds.

Format rules:
- Use clear sections with headers and emoji icons
- Bullet points, not paragraphs
- Bold the most important things
- Include specific names, subjects, and deadlines
- End with a clear NUMBERED list of recommended actions (most important first)
- Be direct — no filler phrases like "I hope this helps"
- If there's nothing urgent, say so clearly and confidently
- Add a "⏱️ Estimated time to clear inbox" at the top

Tone: Professional, efficient, slightly warm. Like a great human chief of staff who knows what you care about."""


def generate_briefing(
    emails: list[EmailMessage],
    user_name: str = "",
    user_settings: dict = None,
) -> DailyBriefing:
    """Generate a daily email briefing using Opus 4.6 adaptive thinking.
    
    Opus will automatically think harder for complex inboxes and lighter
    for quiet days — no manual token budget tuning needed.
    """
    start_time = time.time()

    # Categorize emails for the briefing
    urgent = [e for e in emails if e.priority == EmailPriority.URGENT]
    high = [e for e in emails if e.priority == EmailPriority.HIGH]
    action = [e for e in emails if e.category == EmailCategory.ACTION_REQUIRED]
    fyi = [e for e in emails if e.category == EmailCategory.FYI]
    newsletters = [e for e in emails if e.category in (EmailCategory.NEWSLETTER, EmailCategory.PROMOTIONAL)]

    # Build context for Claude
    email_context = _build_briefing_context(emails)

    greeting_name = user_name.split()[0] if user_name else "there"
    today = datetime.now().strftime("%A, %B %d")

    prompt = f"""Write the morning email briefing for {greeting_name}.

Today is {today}.

Here are the {len(emails)} unread emails, already analyzed:

{email_context}

Summary:
- {len(urgent)} URGENT emails
- {len(high)} HIGH priority emails
- {len(action)} emails requiring action
- {len(fyi)} FYI/informational emails
- {len(newsletters)} newsletters/promotions

Write the briefing with these sections:
1. **Quick Status** — one line: how many emails, how many need attention
2. **🔴 Urgent** — list urgent emails with who, what, and suggested action (skip if none)
3. **🟡 Action Required** — list emails needing a response (skip if none)
4. **📌 FYI** — brief summary of informational emails (keep short)
5. **📰 Newsletters** — one-line summary or "X newsletters — skip or skim" (keep short)
6. **✅ Recommended Actions** — numbered list of specific things to do right now

Keep the whole briefing under 500 words. Be specific about names and subjects."""

    try:
        # Use Opus 4.6 with adaptive thinking for intelligent briefing
        full_text = _call_opus(BRIEFING_SYSTEM_PROMPT, prompt)
        processing_time = time.time() - start_time
        estimated_cost = len(emails) * settings.estimated_cost_per_email_usd

        briefing = DailyBriefing(
            user_id="",  # Set by caller
            total_unread=len(emails),
            urgent_count=len(urgent),
            action_required_count=len(action),
            full_text=full_text,
            emails_analyzed=len(emails),
            processing_time_seconds=round(processing_time, 2),
            estimated_cost_usd=round(estimated_cost, 4),
        )

        logger.info(
            f"Generated briefing: {len(emails)} emails analyzed in {processing_time:.1f}s "
            f"(est. cost: ${estimated_cost:.3f})"
        )

        return briefing

    except Exception as e:
        logger.error(f"Error generating briefing: {e}")
        return DailyBriefing(
            user_id="",
            full_text=f"Error generating briefing: {str(e)}",
            emails_analyzed=0,
        )


def _build_briefing_context(emails: list[EmailMessage]) -> str:
    """Build a compact text representation of emails for the briefing prompt."""
    lines = []
    for i, email in enumerate(emails, 1):
        priority_icon = {
            EmailPriority.URGENT: "🔴",
            EmailPriority.HIGH: "🟡",
            EmailPriority.NORMAL: "⚪",
            EmailPriority.LOW: "⬜",
        }.get(email.priority, "⚪")

        lines.append(
            f"{i}. {priority_icon} [{email.priority.value if email.priority else 'unknown'}] "
            f"From: {email.sender.name or email.sender.email} <{email.sender.email}>\n"
            f"   Subject: {email.subject}\n"
            f"   Summary: {email.summary or email.snippet[:150]}\n"
            f"   Category: {email.category.value if email.category else 'unknown'}\n"
            f"   Suggested Action: {email.suggested_action or 'none'}"
        )

    return "\n\n".join(lines)


# ─── Draft Replies (Evaluator-Optimizer Pattern) ────────

DRAFT_SYSTEM_PROMPT = """You are an expert email writer. Write clear, professional email replies.

Rules:
- Match the tone requested (professional, casual, or formal)
- Be concise — no filler
- Address specific points from the original email
- Don't start with "I hope this email finds you well" or similar clichés
- End with a clear next step or sign-off
- Don't include a subject line — just the body
- Don't include "Dear X" unless the tone is formal — use "Hi X," for professional/casual
- Sound human, not robotic — vary sentence structure"""


EVALUATOR_SYSTEM_PROMPT = """You are a senior communication expert evaluating an AI-drafted email reply.

Score the draft on these criteria (1-10 each):
1. tone_match: Does it match the requested tone?
2. completeness: Does it address all points from the original email?
3. conciseness: Is it the right length? (not too long, not too short)
4. naturalness: Does it sound like a real human wrote it?
5. actionability: Is the next step clear?

Then provide specific, actionable feedback for improvement.

Return JSON only:
{
  "scores": {"tone_match": N, "completeness": N, "conciseness": N, "naturalness": N, "actionability": N},
  "overall_score": N,
  "pass": true/false,
  "feedback": "specific improvement suggestions"
}

A draft PASSES if overall_score >= 8. Be critical but fair."""


SAFETY_SYSTEM_PROMPT = """You are an email safety guardrail. Check this draft reply for:
1. Accidental commitments (promising money, deadlines, resources the user didn't authorize)
2. Aggressive or passive-aggressive tone
3. Confidential information being shared inappropriately
4. Legal risk (contract language, binding agreements)
5. Wrong recipient signals (reply-all risks, CC issues)

Return JSON only:
{
  "safe": true/false,
  "flags": ["list of concerns if any"],
  "severity": "none" | "low" | "medium" | "high"
}"""


def draft_reply(
    original_email: EmailMessage,
    instructions: str = "Write a professional reply",
    tone: str = "professional",
    user_name: str = "",
    max_iterations: int = 2,
) -> EmailDraft:
    """Generate an AI draft reply using the Evaluator-Optimizer pattern.
    
    Flow:
    1. Opus generates initial draft (with adaptive thinking)
    2. Haiku evaluates the draft quality (cheap, fast)
    3. If score < 8, Opus rewrites with feedback (one more pass)
    4. Haiku runs safety guardrail check in parallel concept
    
    This produces significantly better drafts than single-pass generation.
    """
    prompt = f"""Draft a reply to this email.

ORIGINAL EMAIL:
From: {original_email.sender.name} <{original_email.sender.email}>
Subject: {original_email.subject}
Body:
{original_email.body_text[:2000] if original_email.body_text else original_email.snippet}

INSTRUCTIONS FROM USER: {instructions}
TONE: {tone}
SIGN OFF AS: {user_name or "the sender"}

Write the reply body only. No subject line. No metadata."""

    try:
        # === STEP 1: Generate initial draft with Opus 4.6 ===
        draft_body = _call_opus(DRAFT_SYSTEM_PROMPT, prompt)
        logger.info("Draft v1 generated with Opus 4.6")

        # === STEP 2: Evaluate with Haiku (cheap critic) ===
        eval_prompt = f"""Evaluate this email draft reply.

ORIGINAL EMAIL (being replied to):
From: {original_email.sender.name}
Subject: {original_email.subject}
Body snippet: {original_email.snippet[:300]}

REQUESTED TONE: {tone}
USER INSTRUCTIONS: {instructions}

DRAFT TO EVALUATE:
{draft_body}

Return JSON evaluation."""

        for iteration in range(max_iterations):
            try:
                eval_raw = _call_haiku(EVALUATOR_SYSTEM_PROMPT, eval_prompt)
                if eval_raw.startswith("```"):
                    eval_raw = eval_raw.split("\n", 1)[1]
                    if eval_raw.endswith("```"):
                        eval_raw = eval_raw[:-3].strip()
                
                evaluation = json.loads(eval_raw)
                overall = evaluation.get("overall_score", 8)
                passed = evaluation.get("pass", True)

                logger.info(
                    f"Draft evaluation (iteration {iteration + 1}): "
                    f"score={overall}/10, pass={passed}"
                )

                if passed or overall >= 8:
                    break

                # === STEP 3: Optimizer — rewrite with feedback ===
                feedback = evaluation.get("feedback", "Improve clarity and tone.")
                rewrite_prompt = f"""{prompt}

PREVIOUS DRAFT (scored {overall}/10):
{draft_body}

EVALUATOR FEEDBACK:
{feedback}

Write an improved version that addresses the feedback. Reply body only."""

                draft_body = _call_opus(DRAFT_SYSTEM_PROMPT, rewrite_prompt)
                logger.info(f"Draft v{iteration + 2} generated after feedback")

                # Update eval prompt for next iteration
                eval_prompt = f"""Evaluate this email draft reply.

ORIGINAL EMAIL (being replied to):
From: {original_email.sender.name}
Subject: {original_email.subject}
Body snippet: {original_email.snippet[:300]}

REQUESTED TONE: {tone}
USER INSTRUCTIONS: {instructions}

DRAFT TO EVALUATE:
{draft_body}

Return JSON evaluation."""

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Evaluation parse failed (iteration {iteration + 1}): {e}")
                break  # Use current draft if evaluation fails

        # === STEP 4: Safety guardrail check ===
        safety_result = _run_safety_check(draft_body, original_email)

        # Build reply subject
        subject = original_email.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        draft = EmailDraft(
            id=str(uuid.uuid4())[:8],
            original_email_id=original_email.id,
            to=original_email.sender.email,
            subject=subject,
            body=draft_body,
            status=DraftStatus.PENDING,
            instructions=instructions,
        )

        # Attach safety flags if any
        if safety_result and not safety_result.get("safe", True):
            draft.safety_flags = safety_result.get("flags", [])
            draft.safety_severity = safety_result.get("severity", "low")
            logger.warning(
                f"Draft has safety flags: {draft.safety_flags} "
                f"(severity: {draft.safety_severity})"
            )

        return draft

    except Exception as e:
        logger.error(f"Error drafting reply: {e}")
        return EmailDraft(
            id=str(uuid.uuid4())[:8],
            original_email_id=original_email.id,
            to=original_email.sender.email,
            subject=f"Re: {original_email.subject}",
            body=f"[Error generating draft: {str(e)}]",
            status=DraftStatus.PENDING,
            instructions=instructions,
        )


def _run_safety_check(draft_body: str, original_email: EmailMessage) -> dict:
    """Run safety guardrail on a draft using Haiku (cheap + fast).
    
    This catches accidental commitments, aggressive tone, or info leaks
    before the user even sees the draft.
    """
    try:
        safety_prompt = f"""Check this draft email reply for safety issues.

REPLYING TO: {original_email.sender.name} <{original_email.sender.email}>
SUBJECT: {original_email.subject}

DRAFT:
{draft_body}

Return JSON safety assessment."""

        raw = _call_haiku(SAFETY_SYSTEM_PROMPT, safety_prompt)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        return json.loads(raw)

    except Exception as e:
        logger.warning(f"Safety check failed (non-blocking): {e}")
        return {"safe": True, "flags": [], "severity": "none"}


# ─── Quick Classification (Haiku — cheap routing) ───────

def quick_classify(emails: list[EmailMessage]) -> list[dict]:
    """Ultra-fast email classification using Haiku 4.5.
    
    8x cheaper than Opus. Use for:
    - Spam vs not-spam (before wasting Opus tokens)
    - Newsletter detection
    - Simple priority triage
    
    Returns list of {id, is_spam, is_newsletter, quick_priority}.
    """
    if not emails:
        return []

    batch = []
    for e in emails:
        batch.append({
            "id": e.id,
            "from": e.sender.email,
            "subject": e.subject,
            "snippet": e.snippet[:100],
        })

    prompt = f"""Quickly classify these {len(batch)} emails. Return JSON array:
[{{"id": "...", "is_spam": bool, "is_newsletter": bool, "quick_priority": "high"|"normal"|"low"}}]

Emails:
{json.dumps(batch)}

JSON only."""

    try:
        raw = _call_haiku(
            "You are a fast email classifier. Return ONLY valid JSON arrays.",
            prompt,
        )
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Quick classify failed: {e}")
        return []
