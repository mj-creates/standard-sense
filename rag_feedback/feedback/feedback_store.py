import json
from pathlib import Path


# Location of the feedback JSON file
FEEDBACK_FILE = Path("data/feedback/feedback.json")


def _ensure_feedback_file():
    """Create the feedback directory and JSON file if they don't exist."""
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not FEEDBACK_FILE.exists():
        FEEDBACK_FILE.write_text("[]", encoding="utf-8")


def _load_feedback():
    """Load all feedback records from the JSON file."""
    _ensure_feedback_file()

    with open(FEEDBACK_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def _save_feedback(feedback_records):
    """Save feedback records to the JSON file."""
    _ensure_feedback_file()

    with open(FEEDBACK_FILE, "w", encoding="utf-8") as file:
        json.dump(feedback_records, file, indent=2)


def save_feedback(feedback_record):
    """Add one feedback record to the feedback store."""
    feedback_records = _load_feedback()
    feedback_records.append(feedback_record)
    _save_feedback(feedback_records)


def get_feedback_by_spec(spec_id):
    """Return all feedback records for a given specification."""
    feedback_records = _load_feedback()

    return [
        record
        for record in feedback_records
        if record.get("spec_id") == spec_id
    ]