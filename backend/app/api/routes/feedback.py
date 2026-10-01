import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import get_settings
from app.dependencies import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

FEEDBACK_DIR = Path(get_settings().data_dir) / "feedback"
FEEDBACK_FILE = FEEDBACK_DIR / "feedback.json"


class FeedbackSubmission(BaseModel):
    category: str
    priority: str
    content: str
    name: str = "Anonymous"
    email: str = ""


def _load_feedback() -> list[dict]:
    if not FEEDBACK_FILE.exists():
        return []
    try:
        with open(FEEDBACK_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_feedback(entries: list[dict]) -> None:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


@router.post("")
async def submit_feedback(
    submission: FeedbackSubmission,
    user: dict = Depends(get_current_user),
):
    """Submit user feedback."""
    entries = _load_feedback()
    entry = {
        "id": len(entries) + 1,
        "timestamp": datetime.utcnow().isoformat(),
        "category": submission.category,
        "priority": submission.priority,
        "content": submission.content,
        "name": submission.name or user.get("display_name", "Anonymous"),
        "email": submission.email or user.get("email", ""),
        "user_id": user.get("id"),
    }
    entries.append(entry)
    _save_feedback(entries)
    logger.info("Feedback submitted: category=%s priority=%s", submission.category, submission.priority)
    return {"message": "Feedback submitted", "entry": entry}


@router.get("")
async def list_feedback(user: dict = Depends(get_current_user)):
    """List feedback submissions (newest first)."""
    entries = _load_feedback()
    entries.reverse()
    return {"feedback": entries, "total": len(entries)}
