"""
ranking_engine.py
-----------------
Combines semantic search results with compliance checker output to produce
a single ranked list of IS standard recommendations for a given tender spec.

This module is the integration point between two independently developed
sub-systems:

  • semantic_search (Person 1's dev/main branch):
      semantic_search(query_text, top_k) -> list of candidate IS standards
      ranked by embedding similarity (L2 distance; lower = closer match).

      Raw search result shape (internal):
          {
              "rank":        int,
              "is_code":     str,
              "title":       str,
              "description": str,
              "l2_score":    float,   # L2 distance, lower = better
          }

      API-normalised shape (what arrives from the /semantic-search endpoint,
      and what this module accepts as input from callers who go via the API):
          {
              "is_code":     str,
              "title":       str,
              "description": str,
              "score":       float,   # same L2 distance, renamed at API layer
          }

  • compliance_ranking/compliance_checker.py (Person 1's work on this branch):
      check_compliance(spec_parameters, is_code) -> compliance result dict

      Return shape:
          {
              "is_code":        str,
              "status":         "compliant" | "partial" | "non-compliant" | "unknown",
              "passed_fields":  list[str],
              "failed_fields":  list[str],
              "missing_fields": list[str],
          }

      Note: "unknown" is returned when is_code has no entry in
      mock_requirements.json, or when spec_parameters is empty/None.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINAL COMBINED OUTPUT FORMAT  (promised to RAG-Feedback team — do not alter
the top-level key names or the shape of each recommendation object without
coordinating with that team first)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Confident result (semantic search returned "ok"):

    {
        "spec_id":   str,    # caller-supplied identifier for the tender spec
        "spec_text": str,    # the raw query / tender spec text
        "recommendations": [
            {
                "is_code":                  str,
                "title":                    str,
                "semantic_score":           float,  # L2 distance (lower = closer match)
                "compliance_status":        str,    # "compliant" | "partial" |
                                                    # "non-compliant" | "unknown"
                "passed_fields":            list[str],
                "failed_fields":            list[str],  # ALL failed (mandatory + advisory)
                "missing_fields":           list[str],
                "mandatory_failed_fields":  list[str],  # subset of failed_fields
                "advisory_failed_fields":   list[str],  # subset of failed_fields
                "is_mandatory_compliant":   bool,       # True iff zero mandatory fields
                                                        # failed or missing
            },
            ...  sorted by (compliance_tier ASC, semantic_score ASC)
        ]
    }

Backward compatibility note: the original three field lists
(passed_fields, failed_fields, missing_fields) are preserved unchanged.
The three new keys (mandatory_failed_fields, advisory_failed_fields,
is_mandatory_compliant) are additive — existing consumers of the output
(RAG engine, frontend) are unaffected.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RANKING LOGIC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Recommendations are sorted by a two-key tuple:

  Primary:   compliance tier  (ascending integer)
             compliant(0) → partial(1) → unknown(2) → non-compliant(3)

  Secondary: semantic_score   (ascending float, lower L2 = closer match)

Within the same compliance tier, the semantically closer standard ranks
first.  Compliance tier takes precedence over semantic distance because
surfacing a standard the spec actually satisfies is more actionable than
one that merely sounds similar.

Rule-filter use of is_mandatory_compliant:
  - is_mandatory_compliant = True  → the spec meets ALL statutory/safety
    minimums for this IS code.  Advisory shortfalls are informational only.
  - is_mandatory_compliant = False → at least one hard safety/statutory
    requirement is either failed or absent from the spec.  The compliance
    status may still be "partial" (some fields pass) but the rule filter
    flags this standard as conditionally applicable.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PUBLIC API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    rank_recommendations(
        spec_id:         str,
        spec_text:       str,
        spec_parameters: dict,
        semantic_results: list[dict] | dict,
    ) -> dict

    Parameters
    ----------
    spec_id : str
        Caller-supplied identifier for the tender spec (e.g. a UUID or
        filename stem).  Passed through into the output unchanged.
    spec_text : str
        The raw query / tender spec text that was submitted to semantic search.
        Passed through into the output unchanged.
    spec_parameters : dict
        The structured parameter dict extracted from the tender spec by the
        NLP extractor (e.g. {"voltage": "230V AC", "protection": "IP65"}).
        Passed directly to check_compliance() for each candidate IS code.
    semantic_results : list[dict] | dict
        Either:
          • The raw list returned by semantic_search() directly:
                [{"rank":int, "is_code":str, "title":str,
                  "description":str, "l2_score":float}, ...]
          • The API-normalised list from the "results" key of a /semantic-search
            "ok" response:
                [{"is_code":str, "title":str, "description":str, "score":float}]
          • The full needs_clarification dict (if the caller passes the whole
            API response through rather than unwrapping it):
                {"status": "needs_clarification", "question":str, "candidates":[...]}
        All three shapes are detected and handled correctly.

    Returns
    -------
    dict  — the combined output shape documented above.

    rank_results is provided as an alias for backwards compatibility with
    any code that referenced the name from the Prompt 2 docstring.
"""

from __future__ import annotations

import logging
from typing import Any

from compliance_ranking.compliance_checker import check_compliance

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compliance tier ordering
# ---------------------------------------------------------------------------
# This order encodes the tool's core value proposition: a standard that
# fully satisfies procurement requirements (compliant) should surface above
# one that only partially satisfies them (partial), which in turn beats one
# with unverifiable data (unknown), and all of those beat a standard that is
# known to fail requirements (non-compliant).
#
# Using an explicit integer rank rather than a sort key string means the
# ordering is immune to future changes in the string literals used by
# check_compliance(), as long as we update this map alongside them.
_COMPLIANCE_TIER: dict[str, int] = {
    "compliant":     0,   # best — all checked fields pass
    "partial":       1,   # some fields pass, some fail or are missing
    "unknown":       2,   # IS code not in requirements data, or empty spec
    "non-compliant": 3,   # worst — one or more fields actively fail
}
_DEFAULT_TIER = 2  # treat any unexpected status value as "unknown"


def _semantic_score(candidate: dict) -> float:
    """
    Normalise the semantic distance field to a consistent name.

    semantic_search() (called directly) produces "l2_score".
    The /semantic-search API endpoint remaps this to "score".
    We accept both and fall back to 0.0 if neither is present.
    """
    return float(candidate.get("l2_score") or candidate.get("score") or 0.0)


def rank_recommendations(
    spec_id: str,
    spec_text: str,
    spec_parameters: dict[str, Any],
    semantic_results: list[dict] | dict,
) -> dict:
    """
    Combine semantic search candidates with compliance checks and return a
    ranked recommendation list.

    See module docstring for full input/output shape specification.
    """
    # ------------------------------------------------------------------
    # 1. Detect the needs_clarification passthrough case.
    #
    #    Two entry paths:
    #      a) Caller passes the full API response dict straight through
    #         (e.g. they did `response = requests.post(...).json()` and
    #         forwarded it here without unwrapping).
    #      b) Caller passes the raw semantic_search() list but the search
    #         was never actually ambiguous at the source — this shape is
    #         always a list, never a dict, so it can't carry a
    #         needs_clarification status.
    #
    #    If the dict has status == "needs_clarification" there is nothing
    #    to rank — ranking compliance against candidates the search itself
    #    wasn't confident about would produce misleading results.
    # ------------------------------------------------------------------
    if isinstance(semantic_results, dict):
        if semantic_results.get("status") == "needs_clarification":
            # Pass through unchanged. RAG-Feedback / the frontend will
            # collect the user's answer and re-submit the refined query.
            return semantic_results

        # It's an "ok" API response dict — unwrap the results list so the
        # rest of the function deals with a uniform list of candidates.
        candidates: list[dict] = semantic_results.get("results", [])
    else:
        candidates = list(semantic_results)

    # ------------------------------------------------------------------
    # 2. For each candidate, run the compliance checker and build the
    #    enriched entry.
    #
    #    Error handling: check_compliance() is pure Python with no I/O
    #    beyond the module-level JSON load, so exceptions are not expected.
    #    We catch them anyway so that one malformed IS code entry cannot
    #    poison the entire ranking result for the caller.
    # ------------------------------------------------------------------
    enriched: list[dict] = []

    for candidate in candidates:
        is_code = candidate.get("is_code", "")
        score   = _semantic_score(candidate)
        title   = candidate.get("title", "")

        try:
            compliance = check_compliance(spec_parameters, is_code)
        except Exception as exc:  # noqa: BLE001
            # Log the failure with enough context to diagnose later, but
            # keep the candidate in the output so the caller still gets a
            # result for every IS code the search returned.
            logger.error(
                "check_compliance() raised an unexpected exception for "
                "is_code=%r: %s — defaulting to status='unknown'",
                is_code,
                exc,
                exc_info=True,
            )
            compliance = {
                "is_code":        is_code,
                "status":         "unknown",
                "passed_fields":  [],
                "failed_fields":  [],
                "missing_fields": [],
            }

        enriched.append({
            "is_code":                  is_code,
            "title":                    title,
            "semantic_score":           score,
            "compliance_status":        compliance["status"],
            "passed_fields":            compliance["passed_fields"],
            "failed_fields":            compliance["failed_fields"],
            "missing_fields":           compliance["missing_fields"],
            # Rule-filter additions — additive, backward compatible
            "mandatory_failed_fields":  compliance.get("mandatory_failed_fields", []),
            "advisory_failed_fields":   compliance.get("advisory_failed_fields", []),
            "is_mandatory_compliant":   compliance.get("is_mandatory_compliant", False),
            # _tier is a private sort key — stripped before output, never logged
            "_tier":                    _COMPLIANCE_TIER.get(
                                            compliance["status"], _DEFAULT_TIER
                                        ),
        })

    # ------------------------------------------------------------------
    # 3. Sort: primary = compliance tier (ASC), secondary = semantic_score (ASC).
    #    Lower L2 distance = closer semantic match = ranked first within tier.
    # ------------------------------------------------------------------
    enriched.sort(key=lambda r: (r["_tier"], r["semantic_score"]))

    # Strip all private underscore-prefixed sort keys before output.
    # This ensures _tier never appears in API responses or log output.
    _PRIVATE = {"_tier"}
    recommendations = [
        {k: v for k, v in entry.items() if k not in _PRIVATE}
        for entry in enriched
    ]

    return {
        "spec_id":         spec_id,
        "spec_text":       spec_text,
        "recommendations": recommendations,
    }


# Alias for any callers that reference the name from the Prompt 2 docstring.
rank_results = rank_recommendations
