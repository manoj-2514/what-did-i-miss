"""
parser.py - Robust chat parser for 'What Did I Miss?' micro-app.

Parses exported chat transcripts into structured message dictionaries.
Supported formats:
1. Bracketed timestamp:      "[10:32] Rahul: Hey team" or "[2026-10-09 10:32:00] Rahul: Hey team"
2. Standard dash timestamp:   "10:32 - Rahul: Hey team" or "12/10/26, 10:32 - Rahul: Hey team"
3. Discord / Slack format:    "Rahul — 10:32 AM: Hey team" or "Rahul [10:32]: Hey team"
4. Sender-only (no time):     "Rahul: Hey team"
5. Multiline continuation:    Any line without a sender is appended to the previous message.

System lines (e.g., encryption notices) and empty lines are skipped.
Never crashes on malformed or unexpected input.
"""

import re
from typing import List, Dict, Any

# Regular expressions for supported message header formats:
PATTERN_BRACKET = re.compile(
    r"^\[(?P<time>[^\]]+)\]\s*(?P<sender>[^:\n\r]+?):\s*(?P<text>.*)$"
)

PATTERN_DASH = re.compile(
    r"^(?P<time>(?:\d{1,4}[/-]\d{1,2}[/-]\d{1,4}[,\s]+)?\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?)\s*(?:-|—)\s*(?P<sender>[^:\n\r]+?):\s*(?P<text>.*)$"
)

PATTERN_DISCORD_SLACK = re.compile(
    r"^(?P<sender>[^:\n\r\-\—\[]+?)\s*(?:\[|—|-)\s*(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?|(?:\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\s+\d{1,2}:\d{2}))\]?\s*:\s*(?P<text>.*)$"
)

PATTERN_SENDER_ONLY = re.compile(
    r"^(?P<sender>[A-Za-z0-9_\u00C0-\u017F\s\+\(\)\.@'-]{1,40}?):\s*(?P<text>.*)$"
)

# Known system notices or status lines to ignore
SYSTEM_PATTERNS = [
    re.compile(r"messages (?:and calls )?are end-to-end encrypted", re.IGNORECASE),
    re.compile(r"end-to-end encrypted", re.IGNORECASE),
    re.compile(r"<media omitted>", re.IGNORECASE),
    re.compile(r"this message was deleted", re.IGNORECASE),
    re.compile(r"you deleted this message", re.IGNORECASE),
    re.compile(r"created (?:group|this group)", re.IGNORECASE),
    re.compile(r"changed (?:the subject|the group icon|this group's)", re.IGNORECASE),
    re.compile(r"added you", re.IGNORECASE),
    re.compile(r"security code changed", re.IGNORECASE),
    re.compile(r"joined using this group's invite link", re.IGNORECASE),
]


def is_system_line(line: str) -> bool:
    """Return True if the line is an automated system announcement."""
    for pattern in SYSTEM_PATTERNS:
        if pattern.search(line):
            return True
    return False


def clean_line(line: str) -> str:
    """Strip leading/trailing whitespace and invisible Unicode formatting marks (like LTR/RTL/BOM)."""
    return line.strip("\ufeff\u200e\u200f \t\r\n")


def parse_chat(raw: str) -> List[Dict[str, str]]:
    """
    Parse raw chat text into a list of structured message dicts.
    """
    if not raw or not isinstance(raw, str):
        return []

    parsed_messages: List[Dict[str, str]] = []

    try:
        lines = raw.splitlines()
        has_timestamps = any(
            PATTERN_BRACKET.match(clean_line(l)) or PATTERN_DASH.match(clean_line(l)) or PATTERN_DISCORD_SLACK.match(clean_line(l))
            for l in lines
        )

        for raw_line in lines:
            line = clean_line(raw_line)
            if not line:
                continue

            if is_system_line(line):
                continue

            # Try Match 1: [10:32] Rahul: text
            match = PATTERN_BRACKET.match(line)
            if match:
                parsed_messages.append({
                    "sender": match.group("sender").strip(),
                    "time": match.group("time").strip(),
                    "text": match.group("text").strip(),
                })
                continue

            # Try Match 2: 12/10/26, 10:32 - Rahul: text OR 10:32 - Rahul: text
            match = PATTERN_DASH.match(line)
            if match:
                parsed_messages.append({
                    "sender": match.group("sender").strip(),
                    "time": match.group("time").strip(),
                    "text": match.group("text").strip(),
                })
                continue

            # Try Match 3: Discord / Slack format: Rahul — 10:32 AM: text
            match = PATTERN_DISCORD_SLACK.match(line)
            if match:
                parsed_messages.append({
                    "sender": match.group("sender").strip(),
                    "time": match.group("time").strip(),
                    "text": match.group("text").strip(),
                })
                continue

            # Try Match 4: Rahul: text (only when chat has no timestamped headers)
            if not has_timestamps:
                match = PATTERN_SENDER_ONLY.match(line)
                if match:
                    sender_candidate = match.group("sender").strip()
                    if sender_candidate.lower() not in {"http", "https"} and "//" not in sender_candidate:
                        parsed_messages.append({
                            "sender": sender_candidate,
                            "time": "",
                            "text": match.group("text").strip(),
                        })
                        continue

            # If no sender pattern matched, treat as continuation of previous message
            if parsed_messages:
                prev_text = parsed_messages[-1]["text"]
                if prev_text:
                    parsed_messages[-1]["text"] = f"{prev_text} {line}"
                else:
                    parsed_messages[-1]["text"] = line
            else:
                continue

    except Exception as exc:
        print(f"[parser.py] Warning: parsing encountered an unexpected error: {exc}")

    return parsed_messages
