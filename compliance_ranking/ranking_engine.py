"""
ranking_engine.py
-----------------
Combines semantic search candidates with deterministic compliance checks to
produce a ranked list of IS standard recommendations.

Ordering rules:
    1. Primary key:   compliance tier (compliant -> partial -> unknown -> non-compliant)
    2. Secondary key: semantic similarity (L2 distance ascending: lower is better)

Feature 3:
    - Top 5 remain recommendations.
    - Next 3 become also_considered (runner-ups).
"""

from __future__ import annotations

import logging
from typing import Any

from compliance_ranking.compliance_checker import check_compliance

logger = logging.getLogger(__name__)

# Compliance tier ordering
_COMPLIANCE_TIER: dict[str, int] = {
    "compliant": 0,
    "partial": 1,
    "unknown": 2,
    "non-compliant": 3,
}
_DEFAULT_TIER = 2


def _semantic_score(entry: dict[str, Any]) -> float:
    """
    Get semantic similarity score (L2 distance).
    Lower distance = closer semantic match.
    """
    value = entry.get(
        "semantic_score",
        entry.get(
            "l2_score",
            entry.get("score", 0.0),
        ),
    )
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def rank_recommendations(
    spec_id: str,
    spec_text: str,
    spec_parameters: dict[str, Any],
    semantic_results: list[dict[str, Any]] | dict[str, Any],
) -> dict[str, Any]:
    """
    Rank semantic-search candidates using compliance tier first and semantic similarity second.

    Supports:
        - raw list of candidate dicts
        - dict with status == "needs_clarification" (passed through unchanged)
        - dict with status == "ok" and "results" list
    """
    # 1. Handle needs_clarification passthrough
    if isinstance(semantic_results, dict):
        if semantic_results.get("status") == "needs_clarification":
            return semantic_results
        candidates = semantic_results.get("results", [])
    elif isinstance(semantic_results, list):
        candidates = list(semantic_results)
    else:
        candidates = []

    if not isinstance(spec_parameters, dict):
        spec_parameters = {}

    # 2. Check compliance for each candidate and build enriched list
    enriched: list[dict[str, Any]] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        is_code = candidate.get("is_code", "")
        title = candidate.get("title", "")
        score = _semantic_score(candidate)

        try:
            compliance = check_compliance(spec_parameters, is_code)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "check_compliance() raised an unexpected exception for is_code=%r: %s",
                is_code,
                exc,
                exc_info=True,
            )
            compliance = {
                "is_code": is_code,
                "status": "unknown",
                "passed_fields": [],
                "failed_fields": [],
                "missing_fields": [],
                "mandatory_failed_fields": [],
                "advisory_failed_fields": [],
                "is_mandatory_compliant": False,
            }

        import re
        stopwords = {"the", "a", "an", "for", "and", "or", "to", "in", "of", "with", "is", "are", "on", "at", "by", "from", "as", "this", "that"}
        std_text = (candidate.get("title", "") + " " + candidate.get("description", "")).lower()
        spec_text_lower = spec_text.lower()
        std_words = set(re.findall(r'\b[a-z0-9]{3,}\b', std_text))
        matched_terms = [w for w in std_words if w not in stopwords and re.search(r'\b' + re.escape(w) + r'\b', spec_text_lower)]

        entry = dict(candidate)
        entry.update({
            "is_code": is_code,
            "title": title,
            "semantic_score": score,
            "matched_terms": matched_terms,
            "compliance_status": compliance["status"],
            "passed_fields": compliance["passed_fields"],
            "failed_fields": compliance["failed_fields"],
            "missing_fields": compliance["missing_fields"],
            "mandatory_failed_fields": compliance.get("mandatory_failed_fields", []),
            "advisory_failed_fields": compliance.get("advisory_failed_fields", []),
            "is_mandatory_compliant": compliance.get("is_mandatory_compliant", False),
            "_tier": _COMPLIANCE_TIER.get(compliance["status"], _DEFAULT_TIER),
        })

        enriched.append(entry)

    # 3. Sort: primary = compliance tier (ASC), secondary = semantic_score (ASC)
    enriched.sort(key=lambda item: (item["_tier"], item["semantic_score"]))

    # 4. Remove internal sorting field
    all_ranked = [
        {k: v for k, v in entry.items() if k != "_tier"}
        for entry in enriched
    ]

    # 5. Top 5 recommendations and Feature 3 runner-ups
    recommendations = all_ranked[:5]
    runner_ups = all_ranked[5:8]

    also_considered: list[dict[str, Any]] = []
    for entry in runner_ups:
        if entry.get("failed_fields"):
            reason = "Failed on: " + ", ".join(entry["failed_fields"])
        elif entry.get("missing_fields"):
            reason = "Missing: " + ", ".join(entry["missing_fields"])
        else:
            reason = "Lower semantic match"

        also_considered.append({
            "is_code": entry.get("is_code", ""),
            "title": entry.get("title", ""),
            "reason": reason,
        })

    return {
        "spec_id": spec_id,
        "spec_text": spec_text,
        "recommendations": recommendations,
        "also_considered": also_considered,
    }


# Backwards compatibility alias
rank_results = rank_recommendations