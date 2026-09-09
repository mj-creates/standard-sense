# backend/app/officer_history_store.py
"""
Officer History — flat JSON persistence layer.

Follows the same pattern as rag_feedback/feedback/feedback_store.py
so we don't introduce a new database dependency.

Data is stored at:  data/officer_history/actions.json

Each record shape:
{
    "id":                        str (uuid4),
    "officer_id":                str,
    "action_type":               str,   # 'approved' | 'flagged' | 'requested_fix'
    "related_standard_or_spec":  str,
    "notes":                     str | null,
    "timestamp":                 str    (ISO-8601 UTC)
}
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

_STORE_FILE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "officer_history"
    / "actions.json"
)


def _ensure_store() -> None:
    """Create the store file (and parent dirs) if they don't already exist."""
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _STORE_FILE.exists():
        _STORE_FILE.write_text("[]", encoding="utf-8")


def _load() -> list[dict]:
    _ensure_store()
    return json.loads(_STORE_FILE.read_text(encoding="utf-8"))


def _save(records: list[dict]) -> None:
    _ensure_store()
    _STORE_FILE.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ─── Public API ──────────────────────────────────────────────────────────────

def create_action(
    officer_id: str,
    action_type: str,
    related_standard_or_spec: str,
    notes: str | None = None,
) -> dict:
    """Persist one officer action and return the saved record."""
    record = {
        "id":                       str(uuid.uuid4()),
        "officer_id":               officer_id,
        "action_type":              action_type,
        "related_standard_or_spec": related_standard_or_spec,
        "notes":                    notes,
        "timestamp":                datetime.now(timezone.utc).isoformat(),
    }
    records = _load()
    records.append(record)
    _save(records)
    return record


def get_actions_for_officer(
    officer_id: str,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """
    Return a paginated, timestamp-DESC slice of actions for one officer.

    Returns:
        {
            "items":   list[dict],
            "total":   int,   # total matching records (for pagination maths)
            "limit":   int,
            "offset":  int,
        }
    """
    records = _load()
    # Filter to this officer then sort newest-first
    officer_records = sorted(
        [r for r in records if r.get("officer_id") == officer_id],
        key=lambda r: r.get("timestamp", ""),
        reverse=True,
    )
    total = len(officer_records)
    page  = officer_records[offset : offset + limit]
    return {"items": page, "total": total, "limit": limit, "offset": offset}
