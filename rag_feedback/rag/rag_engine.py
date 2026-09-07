"""
rag_engine.py
-------------
RAG explanation and feedback module for StandardSense (Pair A - RAG Module).

Consumes the final output from ML Ranking + Compliance, generates explanatory
prompts via `prompt.py`, and produces structured, factual explanations of
recommended Indian Standards for procurement officers.
"""

from __future__ import annotations

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


def generate_explanation(spec_text: str, recommendation: dict[str, Any]) -> str:
    """
    Generate an explanation for an Indian Standard recommendation using the Groq LLM.

    Calls `build_rag_prompt()` to construct the contextual prompt, sends it
    to the configured Groq LLM via `get_llm()`, and returns the explanation text.

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
        LLM-generated explanation of why the standard was recommended and its compliance standing.

    Raises
    ------
    RuntimeError
        If RAG LLM generation fails during initialization or prompt invocation.
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
        return explanation
    except Exception as exc:
        raise RuntimeError(f"RAG LLM generation failed: {exc}") from exc


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

    explanations: list[dict[str, Any]] = []
    for rec in recommendations:
        explanation_text = generate_explanation(spec_text, rec)
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
