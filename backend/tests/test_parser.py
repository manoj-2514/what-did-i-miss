"""
tests/test_parser.py - Automated tests for parser and heuristics in 'What Did I Miss?'
Can be executed with:
    pytest tests/test_parser.py
or directly with:
    python tests/test_parser.py
"""

import sys
from pathlib import Path

# Ensure the backend/ directory is in sys.path when running this script directly
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from parser import parse_chat
from heuristics import (
    is_mention,
    has_deadline,
    is_question,
    has_urgency,
    has_decision,
    score_message,
    build_attention,
    extract_stats,
)


def test_parser_formats():
    """Verify that all required chat formats and multiline continuations are parsed accurately."""
    # Timestamped chat covering formats 1, 2, and 3
    sample_chat = (
        "Messages are end-to-end encrypted\n"
        "[10:32] Rahul: Hey team, we need to finalize the slides.\n"
        "Can someone take the intro?\n"
        "10:33 - Manoj: Sure, I will do the intro section.\n"
        "12/10/26, 10:35 - Priya: Please finish by 5pm today.\n"
    )

    messages = parse_chat(sample_chat)

    # Total parsed messages in timestamped chat should be 3
    assert len(messages) == 3, f"Expected 3 messages, got {len(messages)}"

    # Format 1: Bracketed timestamp with multiline continuation
    msg0 = messages[0]
    assert msg0["time"] == "10:32"
    assert msg0["sender"] == "Rahul"
    assert msg0["text"] == "Hey team, we need to finalize the slides. Can someone take the intro?"

    # Format 2: Time with dash (10:33 - Manoj: ...)
    msg1 = messages[1]
    assert msg1["time"] == "10:33"
    assert msg1["sender"] == "Manoj"
    assert "Sure, I will do the intro" in msg1["text"]

    # Format 3: WhatsApp export with date & time (12/10/26, 10:35 - Priya: ...)
    msg2 = messages[2]
    assert "12/10/26, 10:35" in msg2["time"]
    assert msg2["sender"] == "Priya"
    assert "finish by 5pm today" in msg2["text"]

    # Format 4: Sender-only format in non-timestamped chat
    sender_chat = (
        "Amit: Don't forget the demo video!\n"
        "Keep it under 2 minutes.\n"
    )
    sender_messages = parse_chat(sender_chat)
    assert len(sender_messages) == 1
    assert sender_messages[0]["time"] == ""
    assert sender_messages[0]["sender"] == "Amit"
    assert sender_messages[0]["text"] == "Don't forget the demo video! Keep it under 2 minutes."

    # FIX 1 Test: in timestamped chat, "Reminder: bring laptop" is merged into previous message
    reminder_chat = "[10:32] Rahul: Meeting at 5\nReminder: bring laptop"
    reminder_msgs = parse_chat(reminder_chat)
    assert len(reminder_msgs) == 1, f"Expected 1 message, got {len(reminder_msgs)}"
    assert "Reminder: bring laptop" in reminder_msgs[0]["text"]

    print("[PASS] All parser formats and continuation merging tested and verified successfully!")


def test_parser_resilience():
    """Verify parser never crashes on empty or malformed input."""
    assert parse_chat("") == []
    assert parse_chat("   \n\n  ") == []
    assert parse_chat("Random malformed text with no colons or valid sender patterns") == []
    assert parse_chat("Messages are end-to-end encrypted") == []
    print("[PASS] Parser resilience and edge cases verified successfully!")


def test_heuristics():
    """Verify deterministic rule-based heuristics with FIX 2 - FIX 5."""
    # Mention
    assert is_mention("Hey @Manoj check this", "Manoj") is True
    assert is_mention("Hey manoj check this", "Manoj") is True
    assert is_mention("Manojkumar is here", "Manoj") is False

    # Deadline & Duration checks (FIX 2, FIX 3, FIX 4)
    assert has_deadline("Submit by 5pm") is True
    assert has_deadline("Due before 6") is True
    assert has_deadline("Meeting on Friday EOD") is True
    assert has_deadline("Submit on 12/10") is True
    assert has_deadline("Cancelled due to rain") is False
    assert has_deadline("We sat there for hours") is False
    assert has_deadline("it takes 2-3 hours") is False
    assert has_deadline("Just casual chat") is False

    # Question vs Imperative checks (FIX 5)
    assert is_question("Are you free?") is True
    assert is_question("Can you review this") is True
    assert is_question("What is the plan") is True
    assert is_question("Do the slides tonight") is False
    assert is_question("Here is the plan.") is False

    # Urgency & Decision
    assert has_urgency("Please send asap") is True
    assert has_decision("We decided to use FastAPI") is True
    assert has_decision("Let's go with option B") is True

    # Scoring
    msg = {"sender": "Rahul", "time": "10:00", "text": "Manoj please finish the report by 5pm today"}
    scored = score_message(msg, "Manoj")
    assert scored["priority"] == "high"
    assert "deadline" in scored["tags"]
    assert "mention" in scored["tags"]

    # Attention building
    attention = build_attention([scored], "Manoj")
    assert len(attention) == 1
    assert attention[0]["reason"] == "mention"

    # User's own messages omitted from their attention list
    user_own_msg = {"sender": "Manoj", "time": "10:05", "text": "I will finish by 5pm", "priority": "high"}
    assert build_attention([user_own_msg], "Manoj") == []

    # Stats
    stats = extract_stats([scored, user_own_msg])
    assert stats["total_messages"] == 2
    assert stats["participants"] == 2

    print("[PASS] Heuristics scoring and attention building verified successfully!")


if __name__ == "__main__":
    test_parser_formats()
    test_parser_resilience()
    test_heuristics()
    print("\nAll unit tests passed successfully!")
