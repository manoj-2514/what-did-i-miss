"""
llm.py - Local AI integration using Ollama for 'What Did I Miss?'
Zero cloud APIs, local-first inference using llama3.2:3b.
"""

import json
import os
import re
from typing import List, Dict, Any, Optional

import httpx

# ============================================================================
# Configuration Constants
# ============================================================================
OLLAMA_URL = "http://localhost:11434"
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "70"))
TIMEOUT = 120

# System prompt tailored for structured extraction
CHUNK_PROMPT = (
    "You analyse part of a group chat for a user named {user_name}. "
    "Reply ONLY with JSON in exactly this shape: "
    '{{"summary": "2-3 sentences", "decisions": ["..."], "action_items": [{{"task": "...", "owner": "name or Unassigned", "deadline": "text or None"}}]}}. '
    "Only include decisions and tasks that are EXPLICITLY stated in the chat. "
    "Never invent names, dates or tasks. If there are none, use empty lists. "
    "Keep each item under 15 words. Ignore jokes, memes and small talk. "
    "The summary must describe what actually happened in this chat, using real names from it. "
    "Copy deadlines exactly as written in the chat; never convert or invent dates. "
    "If no deadline is stated, use None."
)


async def call_ollama(system: str, user: str) -> dict:
    """
    Call Ollama's /api/chat endpoint with JSON mode and return the parsed dict.
    Enforces format='json', temperature=0.2, keep_alive='30m', and num_predict=350.
    """
    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
        "options": {
            "temperature": 0.2,
            "num_ctx": 4096,
            "num_predict": 350,
        },
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        return json.loads(content)


def format_message(m: Dict[str, Any]) -> str:
    """Format single message dictionary as '[time] sender: text'."""
    time_val = m.get("time", "").strip()
    sender = m.get("sender", "Unknown").strip()
    text = m.get("text", "").strip()
    if time_val:
        return f"[{time_val}] {sender}: {text}"
    return f"{sender}: {text}"


def clean_and_validate_result(result: Any) -> Optional[Dict[str, Any]]:
    """
    Validate and sanitize LLM output to guarantee contract compliance.
    Ensures:
      - tldr is a string (invalidates empty, too short, or prompt placeholders)
      - decisions is a list of strings
      - action_items is a list of dicts with string keys task, owner, deadline
    """
    if not isinstance(result, dict):
        return None

    # 1. Validate TLDR / Summary
    raw_tldr = result.get("tldr") or result.get("summary") or ""
    if isinstance(raw_tldr, list):
        tldr = "\n".join(str(item).strip() for item in raw_tldr if str(item).strip())
    elif isinstance(raw_tldr, str):
        tldr = raw_tldr.strip()
    else:
        tldr = str(raw_tldr).strip()

    # Invalidate empty, too-short, or prompt-echo placeholders
    clean_tldr = tldr.lower().strip()
    if (
        not clean_tldr
        or len(clean_tldr) < 15
        or clean_tldr in {"3-4 short lines", "2-3 sentences", "..."}
    ):
        tldr = ""

    # 2. Validate Decisions
    raw_decisions = result.get("decisions", [])
    decisions: List[str] = []
    if isinstance(raw_decisions, list):
        for d in raw_decisions:
            if d and isinstance(d, str) and d.strip():
                decisions.append(d.strip())
            elif d and not isinstance(d, (dict, list)):
                decisions.append(str(d).strip())

    # 3. Validate Action Items
    raw_actions = result.get("action_items", [])
    action_items: List[Dict[str, str]] = []
    if isinstance(raw_actions, list):
        for item in raw_actions:
            if isinstance(item, dict):
                task = str(item.get("task", "")).strip()
                if not task:
                    continue
                owner = str(item.get("owner", "")).strip() or "Unassigned"
                deadline = str(item.get("deadline", "")).strip() or "None"
                action_items.append({
                    "task": task,
                    "owner": owner,
                    "deadline": deadline,
                })

    return {
        "tldr": tldr,
        "decisions": decisions,
        "action_items": action_items,
    }


async def summarize(messages: List[Dict[str, Any]], user_name: str) -> Optional[Dict[str, Any]]:
    """
    Summarize messages using local Ollama instance:
      - <= CHUNK_SIZE messages: single call using CHUNK_PROMPT, map 'summary' to 'tldr'.
      - > CHUNK_SIZE messages: sequential chunk calls, then pure Python merge:
          * tldr: deduplicated non-empty summaries, truncated to <= 3 sentences or 400 chars.
          * decisions: concatenated and deduplicated case-insensitively.
          * action_items: deduplicated by (task, owner); if same task has 'Unassigned'
            and a real owner, keep only the real owner.
      - On ANY failure (connection refused, timeout, invalid JSON), logs reason and returns None.
      - NEVER raises.
    """
    if not messages:
        return None

    user = user_name.strip() if user_name else "User"

    try:
        formatted_lines = [format_message(m) for m in messages]

        # Case 1: CHUNK_SIZE messages or fewer -> Single CHUNK_PROMPT call
        if len(messages) <= CHUNK_SIZE:
            chat_text = "\n".join(formatted_lines)
            system_prompt = CHUNK_PROMPT.format(user_name=user)
            raw_result = await call_ollama(system=system_prompt, user=chat_text)

            # Map "summary" to "tldr" if needed
            if isinstance(raw_result, dict) and "summary" in raw_result and "tldr" not in raw_result:
                raw_result["tldr"] = raw_result.pop("summary")

            cleaned = clean_and_validate_result(raw_result)
            return cleaned

        # Case 2: Greater than CHUNK_SIZE messages -> Sequential chunks & Python merge
        chunk_results: List[Dict[str, Any]] = []
        system_prompt = CHUNK_PROMPT.format(user_name=user)

        for i in range(0, len(formatted_lines), CHUNK_SIZE):
            chunk_slice = formatted_lines[i : i + CHUNK_SIZE]
            chunk_text = "\n".join(chunk_slice)
            raw_chunk = await call_ollama(system=system_prompt, user=chunk_text)
            if isinstance(raw_chunk, dict):
                cleaned_chunk = clean_and_validate_result(raw_chunk)
                if cleaned_chunk:
                    chunk_results.append(cleaned_chunk)

        if not chunk_results:
            print("[llm.py] Sequential chunking produced no valid intermediate results.")
            return None

        # --- Python Merge Stage ---
        # 1. Merge TLDR: deduplicate non-empty summaries in order, truncate to <= 3 sentences or 400 chars
        seen_summaries = set()
        ordered_summaries = []
        for c in chunk_results:
            summary_text = c.get("tldr", "").strip()
            if summary_text and summary_text.lower() not in seen_summaries:
                seen_summaries.add(summary_text.lower())
                ordered_summaries.append(summary_text)

        joined_tldr = " ".join(ordered_summaries).strip()
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", joined_tldr) if s.strip()]
        merged_tldr = " ".join(sentences[:3]) if sentences else joined_tldr
        if len(merged_tldr) > 400:
            merged_tldr = merged_tldr[:400].rstrip()

        # Invalidate if too short or placeholder
        if (
            not merged_tldr
            or len(merged_tldr.lower().strip()) < 15
            or merged_tldr.lower().strip() in {"3-4 short lines", "2-3 sentences", "..."}
        ):
            merged_tldr = ""

        # 2. Merge Decisions: concatenate and deduplicate case-insensitively
        seen_decisions = set()
        merged_decisions: List[str] = []
        for c in chunk_results:
            for d in c.get("decisions", []):
                clean_d = d.strip()
                key = clean_d.lower()
                if clean_d and key not in seen_decisions:
                    seen_decisions.add(key)
                    merged_decisions.append(clean_d)

        # 3. Merge Action Items: deduplicate by (task.lower().strip(), owner.lower())
        raw_actions: List[Dict[str, str]] = []
        for c in chunk_results:
            raw_actions.extend(c.get("action_items", []))

        deduped_actions: List[Dict[str, str]] = []
        seen_task_owner = set()
        for item in raw_actions:
            task_clean = item.get("task", "").strip()
            owner_clean = item.get("owner", "").strip() or "Unassigned"
            deadline_clean = item.get("deadline", "").strip() or "None"
            if not task_clean:
                continue
            pair_key = (task_clean.lower(), owner_clean.lower())
            if pair_key not in seen_task_owner:
                seen_task_owner.add(pair_key)
                deduped_actions.append({
                    "task": task_clean,
                    "owner": owner_clean,
                    "deadline": deadline_clean,
                })

        # If the same task appears with owner "Unassigned" and with a real owner, keep only the real owner
        tasks_with_real_owner = {
            item["task"].lower(): item
            for item in deduped_actions
            if item["owner"].lower() != "unassigned"
        }

        final_action_items: List[Dict[str, str]] = []
        for item in deduped_actions:
            task_key = item["task"].lower()
            if item["owner"].lower() == "unassigned" and task_key in tasks_with_real_owner:
                continue
            final_action_items.append(item)

        return {
            "tldr": merged_tldr,
            "decisions": merged_decisions,
            "action_items": final_action_items,
        }

    except Exception as exc:
        print(f"[llm.py] Summarization failed (falling back to heuristics): {type(exc).__name__}: {exc}")
        return None


async def ollama_ready() -> bool:
    """
    Check if Ollama service is reachable and MODEL is pulled and available.
    Returns True if MODEL is available, False on any error.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                return MODEL in models or f"{MODEL}:latest" in models
    except Exception as exc:
        print(f"[llm.py] ollama_ready check failed: {type(exc).__name__}: {exc}")
    return False


async def warm_up() -> None:
    """
    Send a minimal prompt to load model weights into RAM/VRAM before user demo.
    Swallows all exceptions.
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": MODEL,
                    "stream": False,
                    "format": "json",
                    "keep_alive": "30m",
                    "options": {"num_ctx": 4096, "temperature": 0.2},
                    "messages": [{"role": "user", "content": "Reply with {}"}],
                },
            )
        print(f"[llm.py] Local model '{MODEL}' warmed up and ready in memory.")
    except Exception as exc:
        print(f"[llm.py] Warm-up encountered error (non-fatal): {exc}")
