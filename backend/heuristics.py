"""
heuristics.py - Fast, deterministic heuristic analysis for chat messages.

Contains pure Python rules (no AI / external calls) to analyze urgency, deadlines,
mentions, questions, decisions, and action items with microsecond latency.
"""

import re
from typing import List, Dict, Any

# Precompiled regex patterns for performance and consistency

# Deadlines: relative dates, explicit times ("by 5pm", "before 6"), calendar dates, and keywords
DEADLINE_PATTERNS = [
    re.compile(r"\b(?:today|tomorrow|tonight|eod|end of day|cob|close of business|eow|end of week)\b", re.IGNORECASE),
    re.compile(r"\b(?:deadline|due(?!\s+to)|due date|last date|target date)\b", re.IGNORECASE),
    re.compile(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE),
    re.compile(r"\b(?:mon|tue|wed|thu|fri|sat|sun)\b", re.IGNORECASE),
    # Prepositional time constraints: "by 5pm", "before 6", "by 5:30", "until 8", "at 5pm"
    re.compile(r"\b(?:by|before|until|due(?:\s+by)?|at)\s+\d{1,2}(?::\d{2})?\s*(?:[ap]\.?m\.?)\b", re.IGNORECASE),
    re.compile(r"\b(?:by|before|until)\s+\d{1,2}(?::\d{2})?\b", re.IGNORECASE),
    # Numeric dates: slash-only version (e.g. 12/10, 12/10/26)
    re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"),
    # Month name dates: "12 Oct", "12th October", "Oct 12th"
    re.compile(
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?\b",
        re.IGNORECASE,
    ),
]

# Urgency keywords and expressions
URGENCY_PATTERN = re.compile(
    r"\b(?:urgent|asap|important|immediately|don'?t forget|last chance|critical|emergency|priority|high priority)\b",
    re.IGNORECASE,
)

# Decision markers and confirmation phrases
DECISION_PATTERNS = [
    re.compile(r"\b(?:we decided|let'?s go with|finalized|confirmed|it'?s fixed|done deal)\b", re.IGNORECASE),
    re.compile(r"\b(?:we agree|agreed on|call it settled|decided to|agreed to)\b", re.IGNORECASE),
    re.compile(r"\b(?:decision:|resolution:|approved|locked in|selected option)\b", re.IGNORECASE),
]

# Action Item task phrases / patterns
ACTION_TASK_PATTERNS = [
    re.compile(r"\b(?:please|can you|could you|make sure to|need to|must|will|assigned to|working on)\s+(.+)", re.IGNORECASE),
    re.compile(r"\b(?:i will|i'?ll|i can|let me)\s+(.+)", re.IGNORECASE),
    re.compile(r"\b(?:action item|todo|task):\s*(.+)", re.IGNORECASE),
]

# Question indicators: interrogative starting words or ending with a question mark
QUESTION_START_PATTERN = re.compile(
    r"^(?:what|when|who|where|why|how|can|could|should|is|are|did|do|does)\b",
    re.IGNORECASE,
)


def is_mention(text: str, user_name: str) -> bool:
    """
    Check if the message explicitly mentions the user:
    Matches '@name' or the name as an isolated whole word, case-insensitive.
    """
    if not text or not user_name:
        return False
    name = user_name.strip()
    if not name:
        return False

    pattern = rf"(?i)(?:@|\b){re.escape(name)}\b"
    return bool(re.search(pattern, text))


def has_deadline(text: str) -> bool:
    """
    Detect time constraints and deadlines:
    today, tomorrow, tonight, 'by 5pm', 'before 6', EOD, weekdays,
    dates like 12/10 or 12 Oct, 'deadline', 'due', 'last date'.
    """
    if not text:
        return False
    for pat in DEADLINE_PATTERNS:
        if pat.search(text):
            return True
    return False


def extract_deadline_str(text: str) -> str:
    """Extract matching deadline string snippet or return 'None'."""
    if not text:
        return "None"
    for pat in DEADLINE_PATTERNS:
        match = pat.search(text)
        if match:
            return match.group(0).strip()
    return "None"


def is_question(text: str) -> bool:
    """
    Detect if message is an inquiry:
    Ends with '?' or starts with interrogative verbs/pronouns
    (what/when/who/where/can/did/should, etc.).
    """
    if not text:
        return False
    clean = text.strip()
    if clean.endswith("?"):
        return True
    return bool(QUESTION_START_PATTERN.match(clean))


def has_urgency(text: str) -> bool:
    """Detect urgency markers: urgent, asap, important, immediately, don't forget, last chance."""
    if not text:
        return False
    return bool(URGENCY_PATTERN.search(text))


def has_decision(text: str) -> bool:
    """Detect decisions: 'we decided', 'let's go with', 'finalized', 'confirmed', 'it's fixed', 'done deal'."""
    if not text:
        return False
    for pat in DECISION_PATTERNS:
        if pat.search(text):
            return True
    return False


def score_message(msg: Dict[str, str], user_name: str) -> Dict[str, Any]:
    """
    Score a parsed message and tag its attributes.
    
    Priority Rules:
      - mention AND (deadline or urgent) -> high
      - deadline or urgent -> high
      - mention -> medium (high if it is also a question)
      - question or decision -> medium
      - else -> low
      
    Tags:
      - 'deadline', 'mention', 'question', 'decision'
    """
    text = msg.get("text", "")
    is_ment = is_mention(text, user_name)
    has_dl = has_deadline(text)
    has_urg = has_urgency(text)
    is_q = is_question(text)
    has_dec = has_decision(text)

    if is_ment and (has_dl or has_urg):
        priority = "high"
    elif has_dl or has_urg:
        priority = "high"
    elif is_ment:
        priority = "high" if is_q else "medium"
    elif is_q or has_dec:
        priority = "medium"
    else:
        priority = "low"

    tags: List[str] = []
    if has_dl:
        tags.append("deadline")
    if is_ment:
        tags.append("mention")
    if is_q:
        tags.append("question")
    if has_dec:
        tags.append("decision")

    return {
        "sender": msg.get("sender", ""),
        "time": msg.get("time", ""),
        "text": text,
        "priority": priority,
        "tags": tags,
    }


FIRST_PERSON_COMMITMENT_PATTERN = re.compile(
    r"^\s*(?:i\s+will|i'?ll|i\s+am|i'?m|let\s+me|i\s+can|i\s+shall)\b",
    re.IGNORECASE,
)


def build_attention(messages: List[Dict[str, Any]], user_name: str) -> List[Dict[str, Any]]:
    """
    Select messages that require the user's attention:
      - Mentions the user
      - Carries a deadline
      - Questions directed at the user / group
      
    Each has a single assigned reason adhering to precedence:
      mention > deadline > question
      
    Sorted high priority first, capped at 10 items.
    """
    attention: List[Dict[str, Any]] = []
    clean_user = user_name.strip().lower() if user_name else ""

    for msg in messages:
        sender = msg.get("sender", "").strip().lower()
        if clean_user and sender == clean_user:
            continue

        text = msg.get("text", "")
        reason = None

        if is_mention(text, user_name):
            reason = "mention"
        elif has_deadline(text):
            reason = "deadline"
        elif is_question(text):
            reason = "question"

        if reason:
            if reason in ("deadline", "question") and FIRST_PERSON_COMMITMENT_PATTERN.search(text):
                continue

            attention.append({
                "sender": msg.get("sender", ""),
                "text": text,
                "reason": reason,
                "priority": msg.get("priority", "low"),
            })

    priority_order = {"high": 0, "medium": 1, "low": 2}
    attention.sort(key=lambda item: priority_order.get(item.get("priority", "low"), 3))
    return attention[:10]


def extract_action_items(messages: List[Dict[str, Any]], user_name: str) -> List[Dict[str, str]]:
    """
    Extract actionable tasks, assigned owners, and deadlines deterministically.
    Ensures complete action items extraction even if LLM is unavailable or offline.
    """
    items: List[Dict[str, str]] = []
    seen_tasks = set()

    for msg in messages:
        text = msg.get("text", "").strip()
        sender = msg.get("sender", "").strip()
        if not text:
            continue

        # Check for explicit task assignments or commitments
        has_commit = bool(FIRST_PERSON_COMMITMENT_PATTERN.search(text))
        has_dl = has_deadline(text)
        has_urg = has_urgency(text)
        has_ment = "@" in text or (user_name and is_mention(text, user_name))

        if not (has_commit or has_dl or has_urg or has_ment or "todo" in text.lower() or "task" in text.lower()):
            continue

        # Determine owner
        owner = "Unassigned"
        if has_commit:
            owner = sender if sender else "Unassigned"
        else:
            # Look for @mention or name
            ment_match = re.search(r"@([A-Za-z0-9_]+)", text)
            if ment_match:
                owner = ment_match.group(1).strip()
            elif user_name and is_mention(text, user_name):
                owner = user_name
            elif sender:
                owner = sender

        deadline = extract_deadline_str(text)

        # Truncate text to clean task summary
        clean_task = text
        for pat in ACTION_TASK_PATTERNS:
            m = pat.search(text)
            if m:
                clean_task = m.group(1).strip()
                break

        if len(clean_task) > 120:
            clean_task = clean_task[:120].strip() + "..."

        task_key = clean_task.lower()
        if task_key and task_key not in seen_tasks:
            seen_tasks.add(task_key)
            items.append({
                "task": clean_task,
                "owner": owner,
                "deadline": deadline,
            })

    return items[:10]


def extract_stats(messages: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Extract conversation statistics:
      - total_messages: count of parsed messages
      - participants: count of distinct senders
    """
    senders = {
        m["sender"].strip()
        for m in messages
        if m.get("sender") and m["sender"].strip()
    }
    return {
        "total_messages": len(messages),
        "participants": len(senders),
    }
