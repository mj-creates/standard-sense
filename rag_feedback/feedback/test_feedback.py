
import json

from rag_feedback.feedback.feedback_handler import (
    record_feedback,
    get_feedback,
)

from rag_feedback.feedback.feedback_store import FEEDBACK_FILE


def reset_feedback_file():
    """Clear existing feedback before running tests."""
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(FEEDBACK_FILE, "w", encoding="utf-8") as file:
        json.dump([], file, indent=2)


def test_accept_feedback():
    """Test accepting a recommendation."""

    result = record_feedback(
        spec_id="TENDER_2026_0091",
        standard_id="IS 10322",
        feedback="accepted"
    )

    assert result["spec_id"] == "TENDER_2026_0091"
    assert result["standard_id"] == "IS 10322"
    assert result["feedback"] == "accepted"

    print("[OK] Accept feedback test passed")


def test_reject_feedback():
    """Test rejecting a recommendation."""

    result = record_feedback(
        spec_id="TENDER_2026_0114",
        standard_id="IS 1960",
        feedback="rejected"
    )

    assert result["spec_id"] == "TENDER_2026_0114"
    assert result["standard_id"] == "IS 1960"
    assert result["feedback"] == "rejected"

    print("[OK] Reject feedback test passed")


def test_feedback_with_comment():
    """Test feedback with an officer comment."""

    result = record_feedback(
        spec_id="TENDER_2026_0091",
        standard_id="IS 1554",
        feedback="accepted",
        comment="Correct standard for the PVC cable."
    )

    assert result["feedback"] == "accepted"
    assert result["comment"] == "Correct standard for the PVC cable."

    print("[OK] Feedback with comment test passed")


def test_get_feedback():
    """Test retrieving feedback for a specification."""

    feedback = get_feedback("TENDER_2026_0091")

    assert len(feedback) == 2

    print("[OK] Retrieve feedback test passed")


def test_multiple_feedback_records():
    """Test storing multiple feedback records."""

    record_feedback(
        spec_id="TENDER_2026_0200",
        standard_id="IS 1234",
        feedback="accepted",
        comment="Matches the requirement."
    )

    record_feedback(
        spec_id="TENDER_2026_0200",
        standard_id="IS 5678",
        feedback="rejected",
        comment="Not suitable."
    )

    feedback = get_feedback("TENDER_2026_0200")

    assert len(feedback) == 2
    assert feedback[0]["feedback"] == "accepted"
    assert feedback[1]["feedback"] == "rejected"

    print("[OK] Multiple feedback records test passed")


def test_invalid_feedback():
    """Test that invalid feedback values are rejected."""

    try:
        record_feedback(
            spec_id="TENDER_2026_0300",
            standard_id="IS 9999",
            feedback="maybe"
        )

        assert False, "Invalid feedback should raise ValueError"

    except ValueError:
        print("[OK] Invalid feedback validation test passed")


def run_tests():
    """Run all feedback tests."""

    print("\n" + "=" * 70)
    print("FEEDBACK MODULE TEST SUITE")
    print("=" * 70)

    reset_feedback_file()

    test_accept_feedback()
    test_reject_feedback()
    test_feedback_with_comment()
    test_get_feedback()
    test_multiple_feedback_records()
    test_invalid_feedback()

    print("=" * 70)
    print("ALL FEEDBACK TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_tests()
