from __future__ import annotations

from typing import Any


_COMPLIANCE_TIER = {
    "compliant": 0,
    "partial": 1,
    "unknown": 2,
    "non-compliant": 3,
}


def _semantic_score(entry: dict[str, Any]) -> float:
    """
    Get semantic similarity score.

    Supports the existing score names used by semantic search.
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


def _check_compliance(
    candidate: dict[str, Any],
    spec_parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare a standard's parameters against the tender
    specification and return the complete compliance breakdown.
    """

    standard_parameters = candidate.get(
        "parameters",
        candidate.get("spec_parameters", {}),
    )

    if not isinstance(standard_parameters, dict):
        standard_parameters = {}

    if not isinstance(spec_parameters, dict):
        spec_parameters = {}

    passed_fields: list[str] = []
    failed_fields: list[str] = []
    missing_fields: list[str] = []

    for field, required_value in spec_parameters.items():

        # Ignore empty specification values.
        if required_value in (
            None,
            "",
            [],
            {},
        ):
            continue

        # Standard does not contain this field.
        if field not in standard_parameters:
            missing_fields.append(field)
            continue

        standard_value = standard_parameters[field]

        # Standard contains the field but no value.
        if standard_value in (
            None,
            "",
            [],
            {},
        ):
            missing_fields.append(field)
            continue

        # Compare values.
        if str(
            standard_value
        ).strip().lower() == str(
            required_value
        ).strip().lower():

            passed_fields.append(field)

        else:
            failed_fields.append(field)

    # Determine compliance status.
    if failed_fields:
        compliance_status = "non-compliant"

    elif missing_fields:
        compliance_status = "partial"

    else:
        compliance_status = "compliant"

    return {
        "compliance_status": compliance_status,
        "passed_fields": passed_fields,
        "failed_fields": failed_fields,
        "missing_fields": missing_fields,
    }


def rank_recommendations(
    spec_id: str,
    spec_text: str,
    spec_parameters: dict[str, Any],
    semantic_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Rank semantic-search candidates.

    Existing behavior:
        1. Compliance tier
        2. Semantic similarity

    Feature 3:
        - Top 5 remain recommendations.
        - Next 3 become also_considered.
        - Existing recommendation fields are preserved.
    """

    enriched: list[dict[str, Any]] = []

    for candidate in semantic_results:

        compliance = _check_compliance(
            candidate,
            spec_parameters,
        )

        entry = dict(candidate)

        # Preserve all existing candidate fields.
        entry.update(compliance)

        # Ensure the expected semantic score exists.
        entry["semantic_score"] = _semantic_score(
            candidate
        )

        # Internal sorting key.
        entry["_tier"] = _COMPLIANCE_TIER.get(
            compliance["compliance_status"],
            2,
        )

        enriched.append(entry)

    # Existing ranking behavior:
    # compliance first, semantic similarity second.
    enriched.sort(
        key=lambda item: (
            item["_tier"],
            -item["semantic_score"],
        )
    )

    # Remove only the internal sorting field.
    all_ranked = [
        {
            key: value
            for key, value in entry.items()
            if key != "_tier"
        }
        for entry in enriched
    ]

    # --------------------------------------------------
    # EXISTING TOP RECOMMENDATIONS
    # --------------------------------------------------

    recommendations = all_ranked[:5]

    # --------------------------------------------------
    # FEATURE 3
    # --------------------------------------------------
    #
    # Keep the next three candidates that were considered
    # but did not make the top five.
    #

    runner_ups = all_ranked[5:8]

    also_considered: list[dict[str, Any]] = []

    for entry in runner_ups:

        if entry.get("failed_fields"):

            reason = (
                "Failed on: "
                + ", ".join(
                    entry["failed_fields"]
                )
            )

        elif entry.get("missing_fields"):

            reason = (
                "Missing: "
                + ", ".join(
                    entry["missing_fields"]
                )
            )

        else:

            reason = "Lower semantic match"

        also_considered.append(
            {
                "is_code": entry.get(
                    "is_code",
                    "",
                ),
                "title": entry.get(
                    "title",
                    "",
                ),
                "reason": reason,
            }
        )

    # --------------------------------------------------
    # FINAL RESPONSE
    # --------------------------------------------------

    return {
        "spec_id": spec_id,
        "spec_text": spec_text,
        "recommendations": recommendations,
        "also_considered": also_considered,
    }