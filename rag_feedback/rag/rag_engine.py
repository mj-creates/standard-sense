"""
rag_engine.py
-------------
RAG explanation and feedback module for StandardSense (Pair A - RAG Module).

Consumes the final output from ML Ranking + Compliance, generates explanatory
prompts via `prompt.py`, and produces structured, factual explanations of
recommended Indian Standards for procurement officers.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from rag_feedback.rag.llm import get_llm
from rag_feedback.rag.prompt import build_rag_prompt

VALID_COMPLIANCE_STATUSES = {"compliant", "partial", "non-compliant", "unknown"}
REQUIRED_TOP_LEVEL_FIELDS = ["spec_id", "spec_text", "recommendations"]
REQUIRED_REC_FIELDS = [
    "is_code",
    "title",
    "semantic_score",
    "compliance_status",
    "passed_fields",
    "failed_fields",
    "missing_fields",
]


def validate_input(data: dict[str, Any]) -> None:
    """
    Validate that the input data conforms to the expected ML Ranking + Compliance schema.

    Parameters
    ----------
    data : dict[str, Any]
        Payload from ML Ranking + Compliance module.

    Raises
    ------
    ValueError
        If any mandatory top-level or recommendation fields are missing or invalid.
    """
    if not isinstance(data, dict):
        raise ValueError("Input data must be a dictionary")

    # Handle clarification request payload
    if data.get("status") == "needs_clarification":
        if "question" not in data or not str(data["question"]).strip():
            raise ValueError("Input with status 'needs_clarification' must contain a non-empty 'question' field")
        return

    # Validate top-level fields for normal recommendation payload
    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in data:
            raise ValueError(f"Missing required top-level field: '{field}'")

    if not isinstance(data["recommendations"], list):
        raise ValueError("Field 'recommendations' must be a list")

    # Validate each recommendation item
    for i, rec in enumerate(data["recommendations"]):
        if not isinstance(rec, dict):
            raise ValueError(f"Recommendation at index {i} must be a dictionary")

        for field in REQUIRED_REC_FIELDS:
            if field not in rec:
                raise ValueError(f"Recommendation at index {i} missing required field: '{field}'")

        status = str(rec["compliance_status"]).strip().lower()
        if status not in VALID_COMPLIANCE_STATUSES:
            raise ValueError(
                f"Invalid compliance_status '{rec['compliance_status']}' at index {i}. "
                f"Must be one of: {sorted(VALID_COMPLIANCE_STATUSES)}"
            )


def _generate_template_explanation(spec_text: str, recommendation: dict[str, Any]) -> str:
    """
    Generate a deterministic fallback explanation using only supplied recommendation data.

    Used as a reliable, grounded fallback if LLM initialization, network requests,
    or prompt invocation fails or returns empty output.

    Parameters
    ----------
    spec_text : str
        The procurement specification text.
    recommendation : dict[str, Any]
        Dictionary of recommendation details containing is_code, title, semantic_score,
        compliance_status, passed_fields, failed_fields, and missing_fields.

    Returns
    -------
    str
        Deterministic explanation grounded strictly in the supplied input data.
    """
    is_code = recommendation.get("is_code", "Unknown Standard")
    title = recommendation.get("title", "No Title Provided")
    raw_score = recommendation.get("semantic_score", 0.0)
    score_str = f"{raw_score:.4f}" if isinstance(raw_score, (int, float)) else str(raw_score)
    status = str(recommendation.get("compliance_status", "unknown")).strip().lower()

    passed_fields = recommendation.get("passed_fields", [])
    failed_fields = recommendation.get("failed_fields", [])
    missing_fields = recommendation.get("missing_fields", [])

    status_summaries = {
        "compliant": f"{is_code} is reported as compliant by the compliance module.",
        "partial": f"{is_code} is reported as partially compliant by the compliance module.",
        "non-compliant": f"{is_code} is reported as non-compliant by the compliance module.",
        "unknown": f"Compliance status for {is_code} is reported as unknown.",
    }
    status_summary = status_summaries.get(status, status_summaries["unknown"])

    parts = [
        f"{is_code} ('{title}') was recommended with a semantic score of {score_str} (a lower semantic score indicates a closer match in the ranking system).",
        status_summary,
    ]

    for field in passed_fields:
        parts.append(f"The compliance module reported {field} as passed.")

    for field in failed_fields:
        parts.append(f"The compliance module reported {field} as failed.")

    for field in missing_fields:
        parts.append(f"The compliance module reported {field} as missing.")

    return " ".join(parts)


def generate_explanation(spec_text: str, recommendation: dict[str, Any]) -> str:
    """
    Generate an explanation for an Indian Standard recommendation using the Groq LLM.

    Calls `build_rag_prompt()` to construct the contextual prompt, sends it
    to the configured Groq LLM via `get_llm()`, and returns the explanation text.
    If LLM initialization or invocation fails, times out, or returns an empty result,
    gracefully falls back to the deterministic template explanation.

    Parameters
    ----------
    spec_text : str
        The procurement specification text.
    recommendation : dict[str, Any]
        Dictionary of recommendation details containing is_code, title, semantic_score,
        compliance_status, passed_fields, failed_fields, and missing_fields.

    Returns
    -------
    str
        Explanation of why the standard was recommended and its compliance standing.
    """
    prompt = build_rag_prompt(spec_text, recommendation)

    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        content = response.content
        if isinstance(content, list):
            explanation = "".join(str(part) for part in content).strip()
        else:
            explanation = str(content).strip()

        # Normalize Unicode spaces and hyphens to regular ASCII
        explanation = (
            explanation.replace("\u202f", " ")
            .replace("\u00a0", " ")
            .replace("\u2011", "-")
        )
        if explanation:
            # Strip raw Markdown bold/italic markers so callers never receive
            # literal asterisks. The frontend's _formatExplanation() will apply
            # HTML bold styling from the bullet text, but any non-HTML consumer
            # (PDF export, plain-text copy) gets clean prose.
            # Order matters: strip triple before double before single.
            import re as _re
            explanation = _re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', explanation, flags=_re.DOTALL)
            explanation = _re.sub(r'\*\*(.+?)\*\*',     r'\1', explanation, flags=_re.DOTALL)
            explanation = _re.sub(r'\*(.+?)\*',          r'\1', explanation, flags=_re.DOTALL)
            # Strip markdown headings (### Heading → Heading)
            explanation = _re.sub(r'^#{1,6}\s+', '', explanation, flags=_re.MULTILINE)
            return explanation
    except Exception:
        # Gracefully fall back to the deterministic template explanation
        pass

    return _generate_template_explanation(spec_text, recommendation)


def generate_rag_response(data: dict[str, Any]) -> dict[str, Any]:
    """
    Generate the RAG response for an ML Ranking + Compliance output payload.

    Parameters
    ----------
    data : dict[str, Any]
        Complete output dictionary from ML Ranking + Compliance.

    Returns
    -------
    dict[str, Any]
        StandardSense RAG response dictionary:
        - If status is 'needs_clarification': {"status": "needs_clarification", "question": ...}
        - Otherwise: {"status": "ok", "spec_id": ..., "explanations": [...]}
    """
    validate_input(data)

    if data.get("status") == "needs_clarification":
        return {
            "status": "needs_clarification",
            "question": data["question"],
        }

    spec_id = data["spec_id"]
    spec_text = data["spec_text"]
    recommendations = data.get("recommendations", [])

    if not recommendations:
        return {
            "status": "ok",
            "spec_id": spec_id,
            "explanations": [],
        }

    max_workers = min(len(recommendations), 5)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        explanation_texts = list(
            executor.map(lambda rec: generate_explanation(spec_text, rec), recommendations)
        )

    explanations: list[dict[str, Any]] = []
    for rec, explanation_text in zip(recommendations, explanation_texts):
        explanations.append(
            {
                "is_code": rec.get("is_code", ""),
                "title": rec.get("title", ""),
                "semantic_score": rec.get("semantic_score", 0.0),
                "compliance_status": rec.get("compliance_status", "unknown"),
                "explanation": explanation_text,
            }
        )

    return {
        "status": "ok",
        "spec_id": spec_id,
        "explanations": explanations,
    }
