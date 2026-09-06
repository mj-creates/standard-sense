"""
prompt.py
---------
Prompt generation module for the StandardSense RAG explanation system.

Constructs structured prompts for LLM inference to explain recommendations
and compliance assessments against Indian Standards (IS) for procurement officers.
"""

from __future__ import annotations

from typing import Any, Mapping


def build_rag_prompt(spec_text: str, recommendation: Mapping[str, Any] | dict[str, Any]) -> str:
    """
    Build a clear explanation prompt for an LLM to evaluate and explain an Indian Standard recommendation.

    Parameters
    ----------
    spec_text : str
        The procurement specification text.
    recommendation : Mapping[str, Any] | dict[str, Any]
        Dictionary containing recommendation and compliance details:
        - "is_code": Indian Standard code (e.g., "IS 1554")
        - "title": Title of the Indian Standard
        - "semantic_score": Semantic distance / similarity score (lower is closer)
        - "compliance_status": Compliance status ('compliant', 'partial', 'non-compliant', 'unknown')
        - "passed_fields": List of fields that passed compliance
        - "failed_fields": List of fields that failed compliance
        - "missing_fields": List of required fields missing from the tender or standard

    Returns
    -------
    str
        Generated prompt string ready for LLM consumption.
    """
    is_code = recommendation.get("is_code", "Unknown Standard")
    title = recommendation.get("title", "No Title Provided")
    raw_score = recommendation.get("semantic_score", "N/A")
    if isinstance(raw_score, (int, float)):
        semantic_score_str = f"{raw_score:.4f}"
    else:
        semantic_score_str = str(raw_score)

    raw_status = str(recommendation.get("compliance_status", "unknown")).strip().lower()
    valid_statuses = {"compliant", "partial", "non-compliant", "unknown"}
    compliance_status = raw_status if raw_status in valid_statuses else "unknown"

    passed_fields = recommendation.get("passed_fields", [])
    failed_fields = recommendation.get("failed_fields", [])
    missing_fields = recommendation.get("missing_fields", [])

    passed_str = ", ".join(str(f) for f in passed_fields) if passed_fields else "None"
    failed_str = ", ".join(str(f) for f in failed_fields) if failed_fields else "None"
    missing_str = ", ".join(str(f) for f in missing_fields) if missing_fields else "None"

    status_descriptions = {
        "compliant": "The specification fully satisfies all evaluated requirements of this standard.",
        "partial": "The specification partially satisfies requirements, with missing or unverified fields.",
        "non-compliant": "The specification fails one or more requirements of this standard.",
        "unknown": "Compliance cannot be conclusively determined from the available specification data.",
    }
    status_note = status_descriptions.get(compliance_status, status_descriptions["unknown"])

    prompt = f"""You are an expert technical advisor for government procurement in India, evaluating tender specifications against Bureau of Indian Standards (BIS).

Explain why the following Indian Standard was recommended for this procurement specification, and summarize the compliance assessment clearly and concisely for a procurement officer.

### Context & Input Data
1. Procurement Specification:
   "{spec_text}"

2. Recommended Standard:
   - IS Code: {is_code}
   - Title: {title}
   - Semantic Score: {semantic_score_str} (Note: a lower semantic score means a closer semantic match)

3. Compliance Assessment:
   - Compliance Status: {compliance_status} ({status_note})
   - Passed Fields: {passed_str}
   - Failed Fields: {failed_str}
   - Missing Fields: {missing_str}

### Instructions
Provide a concise, professional explanation covering the following:
1. Relevance: Explain why this standard is relevant to the tender product and requirements. Mention that the semantic score of {semantic_score_str} indicates how closely the tender description matches the standard (noting that a lower semantic score means a closer semantic match).
2. Field Matching: Detail which specification fields matched ({passed_str}).
3. Gaps & Issues: Explain any failed fields ({failed_str}) or missing fields ({missing_str}).
4. Compliance Status: Clearly state the overall compliance status as "{compliance_status}".
5. Constraints:
   - Base your explanation strictly on the facts and data provided above.
   - Never invent requirements or facts that are not provided.
   - Keep the explanation concise and suitable for a procurement officer.
"""
    return prompt.strip()
