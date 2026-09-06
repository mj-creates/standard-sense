from .feedback_store import save_feedback, get_feedback_by_spec


VALID_FEEDBACK = {"accepted", "rejected"}


def record_feedback(spec_id, standard_id, feedback, comment=""):
    """
    Record officer feedback for a recommended standard.
    """

    if feedback not in VALID_FEEDBACK:
        raise ValueError(
            "Feedback must be either 'accepted' or 'rejected'."
        )

    feedback_record = {
        "spec_id": spec_id,
        "standard_id": standard_id,
        "feedback": feedback,
        "comment": comment
    }

    save_feedback(feedback_record)

    return feedback_record


def get_feedback(spec_id):
    """
    Retrieve all feedback records for a specification.
    """

    return get_feedback_by_spec(spec_id)