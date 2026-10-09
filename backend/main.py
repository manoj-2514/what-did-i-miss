"""
main.py - FastAPI Backend for 'What Did I Miss?'
A local-first, privacy-preserving micro-app for summarizing group chats.

Run locally with:
    uvicorn main:app --reload --port 8000
"""

import asyncio
import os
import re
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure backend directory is in sys.path for robust imports whether run
# from backend/ ("uvicorn main:app") or from workspace root.
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from parser import parse_chat
    from heuristics import score_message, build_attention, extract_stats
    from llm import summarize, ollama_ready, warm_up, MODEL
except ImportError:
    from backend.parser import parse_chat
    from backend.heuristics import score_message, build_attention, extract_stats
    from backend.llm import summarize, ollama_ready, warm_up, MODEL

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


# ============================================================================
# FastAPI Lifespan Handler (Non-blocking warm-up on startup)
# ============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Trigger background warm-up of Ollama model so model weights are preloaded into memory
    asyncio.create_task(warm_up())
    yield


# ============================================================================
# FastAPI App Initialization
# ============================================================================
app = FastAPI(
    title="What Did I Miss? - Local Backend",
    description="Local-first micro-app to parse and summarize group chats without external cloud APIs.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration allowing all origins (for local development & frontend ports)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Pydantic Models for Strict API Contract (Never rename fields)
# ============================================================================
class AnalyzeRequest(BaseModel):
    user_name: str = Field(default="", description="Name of the user requesting the catch-up summary")
    chat: str = Field(..., description="Raw text transcript pasted from a group chat")


class AttentionItem(BaseModel):
    sender: str
    text: str
    reason: str  # "mention" | "deadline" | "question"
    priority: str  # "high" | "medium" | "low"


class ActionItem(BaseModel):
    task: str
    owner: str
    deadline: str


class MessageItem(BaseModel):
    sender: str
    time: str
    text: str
    priority: str  # "high" | "medium" | "low"
    tags: List[str]


class StatsItem(BaseModel):
    total_messages: int
    participants: int


class AnalyzeResponse(BaseModel):
    tldr: str
    attention: List[AttentionItem]
    decisions: List[str]
    action_items: List[ActionItem]
    messages: List[MessageItem]
    stats: StatsItem
    ai_used: bool = False


# ============================================================================
# API Routes
# ============================================================================
@app.get("/health", tags=["System"])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint verifying backend status and local Ollama readiness."""
    is_ollama_available = await ollama_ready()
    return {
        "status": "ok",
        "ollama": is_ollama_available,
        "model": MODEL,
    }


@app.post("/analyze", response_model=AnalyzeResponse, tags=["Analysis"])
async def analyze_chat(req: AnalyzeRequest) -> AnalyzeResponse:
    """
    Analyze raw chat text:
    1. Parse raw transcript into structured messages.
    2. Score priority and assign heuristic tags.
    3. Extract high-priority attention items directed at the user.
    4. Compile decisions and conversation statistics.
    5. Run local AI summarization via Ollama (fallback to heuristics on error).
    6. Return structured response sorted by priority.
    """
    user_name = req.user_name.strip()
    raw_chat = req.chat

    # Stage 0: Validate Input
    if not raw_chat or not raw_chat.strip():
        raise HTTPException(
            status_code=400,
            detail="Chat text cannot be empty. Please paste your chat transcript.",
        )

    # Stage 1: Parse
    parsed_messages = parse_chat(raw_chat)
    if not parsed_messages:
        raise HTTPException(
            status_code=400,
            detail="No valid messages could be parsed from the provided text. Please ensure valid chat format.",
        )
    print(f"[Analyze] Stage 1: Parsed {len(parsed_messages)} messages from raw input.")

    # Stage 2: Heuristic Scoring & Tagging
    scored_messages = [score_message(msg, user_name) for msg in parsed_messages]
    attention_items = build_attention(scored_messages, user_name)
    stats_data = extract_stats(scored_messages)
    print(f"[Analyze] Stage 2: Scored {len(scored_messages)} messages, identified {len(attention_items)} attention items.")

    # Extract heuristic decisions
    heuristic_decisions = [
        msg["text"]
        for msg in scored_messages
        if "decision" in msg.get("tags", [])
    ]

    # Baseline heuristic TLDR (used as default / fallback)
    high_priority_msgs = [m for m in scored_messages if m["priority"] == "high"]
    if high_priority_msgs:
        tldr_snippets = [f"{m['sender']}: {m['text']}" for m in high_priority_msgs[:3]]
        heuristic_tldr = "Key Highlights: " + " | ".join(tldr_snippets)
    elif scored_messages:
        tldr_snippets = [f"{m['sender']}: {m['text']}" for m in scored_messages[:3]]
        heuristic_tldr = "Summary: " + " | ".join(tldr_snippets)
    else:
        heuristic_tldr = "No messages available to summarize."

    # ========================================================================
    # Stage 3: Local AI Inference (Ollama)
    # ========================================================================
    # PERFORMANCE OPTIMIZATION: A CPU-only 3B model spends most of its time
    # reading input, so for chats of more than 25 messages we drop pure small talk
    # but keep anything that could be a task: every message with priority medium or
    # high, plus every message matching commitment phrases, plus the one message
    # before each selected message for context (deduplicated in chronological order).
    # Chats of 25 messages or fewer are sent in full.
    if len(scored_messages) > 25:
        commitment_pattern = re.compile(
            r"\b(?:i\s+will|i'?ll|will\s+\w+|let\s+me|i\s+can|volunteer|take\s+care|handle|working\s+on|assigned|please)\b",
            re.IGNORECASE,
        )
        relevant_indices = set()
        for idx, msg in enumerate(scored_messages):
            text = msg.get("text", "")
            if msg.get("priority") in ("high", "medium") or commitment_pattern.search(text):
                if idx > 0:
                    relevant_indices.add(idx - 1)
                relevant_indices.add(idx)
        llm_input_messages = [scored_messages[i] for i in sorted(relevant_indices)]
    else:
        llm_input_messages = scored_messages

    # Execute LLM summarization with timing
    start_llm = time.perf_counter()
    llm_result = await summarize(llm_input_messages, user_name)
    llm_duration = time.perf_counter() - start_llm
    print(f"[Analyze] Stage 3: LLM inference completed in {llm_duration:.2f}s.")

    # Determine final TLDR, decisions, and action items
    if llm_result is not None:
        ai_used = True
        tldr = llm_result.get("tldr") or heuristic_tldr

        # Combine LLM decisions + heuristic decisions, deduplicated case-insensitively
        llm_decisions = llm_result.get("decisions", [])
        combined_decisions: List[str] = []
        seen_decisions = set()
        for d in (llm_decisions + heuristic_decisions):
            clean_d = d.strip()
            key = clean_d.lower()
            if clean_d and key not in seen_decisions:
                seen_decisions.add(key)
                combined_decisions.append(clean_d)
        decisions = combined_decisions

        # Action items parsed from LLM
        action_items = [ActionItem(**item) for item in llm_result.get("action_items", [])]
    else:
        ai_used = False
        tldr = heuristic_tldr
        decisions = heuristic_decisions
        action_items = []
        print("[Analyze] Using deterministic heuristics fallback (ai_used=False).")

    # Sort messages: high -> medium -> low (stable sort preserving chronological order within tiers)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_messages = sorted(
        scored_messages,
        key=lambda m: priority_order.get(m.get("priority", "low"), 3),
    )

    print(f"[Analyze] Stage 4: Returning response (ai_used={ai_used}).")

    return AnalyzeResponse(
        tldr=tldr,
        attention=[AttentionItem(**item) for item in attention_items],
        decisions=decisions,
        action_items=action_items,
        messages=[MessageItem(**item) for item in sorted_messages],
        stats=StatsItem(**stats_data),
        ai_used=ai_used,
    )


# ============================================================================
# Static Files Mounts (Mounted LAST to avoid intercepting API routes)
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent
SAMPLE_CHATS_DIR = (BASE_DIR / ".." / "sample_chats").resolve()
FRONTEND_DIR = (BASE_DIR / ".." / "frontend" / "dist").resolve()
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = (BASE_DIR / ".." / "frontend").resolve()

# Serve ../sample_chats at /sample_chats if the folder exists
if SAMPLE_CHATS_DIR.exists():
    app.mount("/sample_chats", StaticFiles(directory=str(SAMPLE_CHATS_DIR)), name="sample_chats")

# Serve ../frontend at "/" with html=True if the folder exists
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
