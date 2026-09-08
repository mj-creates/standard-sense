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

    prompt = f"""You are a technical advisor for government procurement in India, evaluating tender specifications against Bureau of Indian Standards (BIS).

Explain why the following Indian Standard was recommended for this procurement specification, and summarize the compliance assessment clearly and concisely for a procurement officer.

You must ONLY use information explicitly present in the input data below. Do not use external knowledge or invent facts.

### Ground Truth Input Data
- Procurement Specification (spec_text): "{spec_text}"
- Recommended Standard (is_code): {is_code}
- Standard Title (title): {title}
- Semantic Score (semantic_score): {semantic_score_str}
- Compliance Status (compliance_status): {compliance_status}
- Passed Fields (passed_fields): {passed_str}
- Failed Fields (failed_fields): {failed_str}
- Missing Fields (missing_fields): {missing_str}

### Explicit Instructions & Anti-Hallucination Guidelines
1. NEVER use words such as "covered", "matches the scope", "meets the criteria", "satisfies the requirements", "complies with the standard", or similar wording to describe a field unless the actual standard requirement is explicitly present in the input.
2. A field listed in passed_fields means ONLY:
   "The compliance module reported [field_name] as passed." (e.g., "The compliance module reported protection_rating as passed.", "The compliance module reported voltage as passed.")
   It does NOT mean that you know why it passed.
3. A field listed in failed_fields means ONLY:
   "The compliance module reported this field as failed." (or "The compliance module reported [field_name] as failed.")
4. A field listed in missing_fields means ONLY:
   "The compliance module reported [field_name] as missing." (or "The compliance module reported this field as missing.")
   Do NOT say that the standard does or does not cover that field. NEVER explain why fields are missing or whether the standard covers them.
5. Do not infer relationships between the specification values and the standard from the standard title, standard code, semantic score, or field names. Do not infer or invent the actual technical requirements of the Indian Standard from its title or code.
6. Do not say that a recommendation is "suitable", "applicable", "valid", or "appropriate" unless that conclusion is explicitly provided in the input.
7. The explanation for why the standard was recommended must be strictly limited to:
   - the standard code and title provided,
   - the semantic score provided by the ranking system (stating that a lower score indicates a closer match in the ranking system),
   - and the fact that the ranking/compliance modules produced the supplied results.
8. For compliance status, simply report:
   "The compliance module evaluated the overall status as {compliance_status}."
9. Do not invent standard requirements, standard clauses, certification requirements, warranty requirements, voltage limits, IP ratings, materials, or other technical facts.
10. Explain only the matching information supplied by the ranking/compliance module. If the available information is insufficient to explain why a field matches, say that it is "reported as passed by the compliance module" rather than inventing a reason.
11. Keep the explanation concise, strictly factual, and suitable for a procurement officer.

### Output Formatting
- Use Markdown formatting.
- Use **bold** for important labels, IS codes, compliance status, and key values.
- Use *italic* only when useful.
- Use bullet points for recommendation and compliance details.
- Do not use tables.
- Do not output raw JSON.
"""
    return prompt.strip()
