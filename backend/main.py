"""
main.py - FastAPI Backend for 'What Did I Miss?'
A local-first, privacy-preserving micro-app for summarizing group chats.

Run locally with:
    uvicorn main:app --reload --port 8000
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# Ensure backend directory is in sys.path for robust imports whether run
# from backend/ ("uvicorn main:app") or from workspace root.
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from parser import parse_chat
    from heuristics import score_message, build_attention, extract_stats
except ImportError:
    from backend.parser import parse_chat
    from backend.heuristics import score_message, build_attention, extract_stats

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ============================================================================
# FastAPI App Initialization
# ============================================================================
app = FastAPI(
    title="What Did I Miss? - Local Backend",
    description="Local-first micro-app to parse and summarize group chats without external cloud APIs.",
    version="1.0.0",
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


# ============================================================================
# API Routes
# ============================================================================
@app.get("/health", tags=["System"])
def health_check() -> Dict[str, str]:
    """Health check endpoint to verify backend status."""
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse, tags=["Analysis"])
async def analyze_chat(req: AnalyzeRequest) -> AnalyzeResponse:
    """
    Analyze raw chat text:
    1. Parse raw transcript into structured messages.
    2. Score priority and assign heuristic tags.
    3. Extract high-priority attention items directed at the user.
    4. Compile decisions and conversation statistics.
    5. Return structured response sorted by priority.
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

    # Extract Decisions tagged by heuristics
    decisions = [
        msg["text"]
        for msg in scored_messages
        if "decision" in msg.get("tags", [])
    ]

    # Action Items (placeholder for next step)
    action_items: List[ActionItem] = []

    # Temporary TLDR built from the top 3 high-priority messages
    high_priority_msgs = [m for m in scored_messages if m["priority"] == "high"]
    if high_priority_msgs:
        tldr_snippets = [f"{m['sender']}: {m['text']}" for m in high_priority_msgs[:3]]
        tldr = "Key Highlights: " + " | ".join(tldr_snippets)
    elif scored_messages:
        tldr_snippets = [f"{m['sender']}: {m['text']}" for m in scored_messages[:3]]
        tldr = "Summary: " + " | ".join(tldr_snippets)
    else:
        tldr = "No messages available to summarize."

    # ========================================================================
    # LLM PLACEHOLDER (Step 2 Integration)
    # In the next step, a local LLM module (llm.py) will be plugged in here to
    # generate an AI-powered TLDR summary, extract decisions, and identify action items:
    #
    # try:
    #     from llm import analyze_with_local_llm
    #     llm_output = await analyze_with_local_llm(scored_messages, user_name)
    #     tldr = llm_output.get("tldr", tldr)
    #     decisions = llm_output.get("decisions", decisions)
    #     action_items = [ActionItem(**item) for item in llm_output.get("action_items", [])]
    # except ImportError:
    #     pass  # llm.py not yet implemented
    # ========================================================================

    # Sort messages: high -> medium -> low (stable sort preserving chronological order within tiers)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_messages = sorted(
        scored_messages,
        key=lambda m: priority_order.get(m.get("priority", "low"), 3),
    )

    print(f"[Analyze] Stage 3: Completed analysis. Returning response.")

    return AnalyzeResponse(
        tldr=tldr,
        attention=[AttentionItem(**item) for item in attention_items],
        decisions=decisions,
        action_items=action_items,
        messages=[MessageItem(**item) for item in sorted_messages],
        stats=StatsItem(**stats_data),
    )


# ============================================================================
# Static Files Mounts (Mounted LAST to avoid intercepting API routes)
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent
SAMPLE_CHATS_DIR = (BASE_DIR / ".." / "sample_chats").resolve()
FRONTEND_DIR = (BASE_DIR / ".." / "frontend").resolve()

# Serve ../sample_chats at /sample_chats if the folder exists
if SAMPLE_CHATS_DIR.exists():
    app.mount("/sample_chats", StaticFiles(directory=str(SAMPLE_CHATS_DIR)), name="sample_chats")

# Serve ../frontend at "/" with html=True if the folder exists
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
