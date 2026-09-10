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

LLM compliance fast-path:
    - Standards in mock_requirements.json → checked via deterministic
      check_compliance() (no network call, instant).
    - Standards NOT in mock_requirements.json → checked via
      extract_and_check_compliance_llm() (Groq call, 8 s timeout).
    - LLM calls for the top-5 recommendation candidates run IN PARALLEL
      via ThreadPoolExecutor to minimise end-to-end latency.
    - also_considered (ranks 6-8) skip LLM compliance — they don't need
      full detail in the UI and keeping them fast matters more.
    - Results are cached in-memory inside llm_compliance.py across requests.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from compliance_ranking.compliance_checker import _REQUIREMENTS, check_compliance
from compliance_ranking.llm_compliance import extract_and_check_compliance_llm

logger = logging.getLogger(__name__)

# Compliance tier ordering — "unknown" sits between partial and non-compliant
# so that LLM-assessed unknowns don't bury real partial matches.
_COMPLIANCE_TIER: dict[str, int] = {
    "compliant":     0,
    "partial":       1,
    "unknown":       2,
    "non-compliant": 3,
}
_DEFAULT_TIER = 2


def _semantic_score(entry: dict[str, Any]) -> float:
    """Return the L2 semantic similarity score (lower = closer match)."""
    value = entry.get(
        "semantic_score",
        entry.get("l2_score", entry.get("score", 0.0)),
    )
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _run_compliance(
    candidate: dict[str, Any],
    spec_parameters: dict[str, Any],
    use_llm: bool,
) -> dict:
    """
    Dispatch compliance check for a single candidate.

    Fast path  (use_llm=False OR is_code in _REQUIREMENTS):
        check_compliance() — deterministic, no network.

    LLM path   (use_llm=True AND is_code NOT in _REQUIREMENTS):
        extract_and_check_compliance_llm() — Groq call, 8 s cap, cached.
    """
    is_code     = candidate.get("is_code", "")
    title       = candidate.get("title", "")
    description = candidate.get("description", "")

    if is_code in _REQUIREMENTS:
        # Legacy fast path — deterministic rule check
        try:
            return check_compliance(spec_parameters, is_code)
        except Exception as exc:  # noqa: BLE001
            logger.error("check_compliance() raised for %r: %s", is_code, exc, exc_info=True)
            return {
                "is_code": is_code, "status": "unknown",
                "passed_fields": [], "failed_fields": [], "missing_fields": [],
                "mandatory_failed_fields": [], "advisory_failed_fields": [],
                "is_mandatory_compliant": False,
            }

    if use_llm:
        # Dynamic LLM path for unmapped standards
        return extract_and_check_compliance_llm(
            spec_parameters=spec_parameters,
            is_code=is_code,
            title=title,
            description=description,
        )

    # also_considered slot — skip LLM, return neutral unknown quickly
    return {
        "is_code": is_code, "status": "unknown",
        "passed_fields": [], "failed_fields": [], "missing_fields": [],
        "mandatory_failed_fields": [], "advisory_failed_fields": [],
        "is_mandatory_compliant": None,
    }


def rank_recommendations(
    spec_id: str,
    spec_text: str,
    spec_parameters: dict[str, Any],
    semantic_results: list[dict[str, Any]] | dict[str, Any],
) -> dict[str, Any]:
    """
    Rank semantic-search candidates using compliance tier first and
    semantic similarity second.

    Accepts:
        - raw list of candidate dicts
        - dict with status == "needs_clarification" (passed through unchanged)
        - dict with status == "ok" containing a "results" list
    """
    # ── 1. Unpack input ──────────────────────────────────────────────────────
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

    # ── 2. Identify explicitly cited IS codes in spec text ───────────────────
    explicit_codes: set[str] = set()
    for key in ["is_code", "standard", "standard_code", "code"]:
        val = spec_parameters.get(key)
        if isinstance(val, str) and "IS" in val.upper():
            explicit_codes.add(val.replace(" ", "").replace(":", "").upper())

    for c in re.findall(r'IS\s*:?\s*\d+(?:-\d+)*', spec_text, re.IGNORECASE):
        explicit_codes.add(c.replace(" ", "").replace(":", "").upper())

    # ── 3. Partition candidates: top-5 get LLM, rest get fast skip ───────────
    valid_candidates = [c for c in candidates if isinstance(c, dict)]

    # We want LLM for up to the first 5 non-legacy candidates. Determine
    # which slots need LLM calls before we start them.
    llm_slots: set[int] = set()
    legacy_count = 0
    for idx, c in enumerate(valid_candidates[:8]):
        if c.get("is_code", "") not in _REQUIREMENTS:
            # Mark for LLM only while we still have room in the top-5 LLM budget
            if (idx - legacy_count) < 5:
                llm_slots.add(idx)
        else:
            legacy_count += 1

    # ── 4. Run compliance checks (parallel for LLM slots) ───────────────────
    compliance_results: dict[int, dict] = {}

    # Collect which indices need LLM calls
    llm_indices = [i for i in range(len(valid_candidates[:8])) if i in llm_slots]
    non_llm_indices = [i for i in range(len(valid_candidates[:8])) if i not in llm_slots]

    # Non-LLM (sync, fast) — run first so we can return immediately if LLM fails
    for idx in non_llm_indices:
        compliance_results[idx] = _run_compliance(
            valid_candidates[idx], spec_parameters, use_llm=False
        )

    # LLM calls — parallel, capped at 5 workers (one per recommendation slot)
    if llm_indices:
        max_workers = min(len(llm_indices), 5)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_idx = {
                pool.submit(
                    _run_compliance, valid_candidates[i], spec_parameters, True
                ): i
                for i in llm_indices
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    compliance_results[idx] = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Parallel compliance future raised for candidate[%d]: %s",
                        idx, exc, exc_info=True,
                    )
                    compliance_results[idx] = {
                        "is_code": valid_candidates[idx].get("is_code", ""),
                        "status": "unknown",
                        "passed_fields": [], "failed_fields": [], "missing_fields": [],
                        "mandatory_failed_fields": [], "advisory_failed_fields": [],
                        "is_mandatory_compliant": None,
                    }

    # ── 5. Build enriched candidate list ─────────────────────────────────────
    stopwords = {
        "the", "a", "an", "for", "and", "or", "to", "in", "of",
        "with", "is", "are", "on", "at", "by", "from", "as", "this", "that",
    }
    spec_text_lower = spec_text.lower()

    enriched: list[dict[str, Any]] = []

    for idx, candidate in enumerate(valid_candidates[:8]):
        is_code = candidate.get("is_code", "")
        title   = candidate.get("title", "")
        score   = _semantic_score(candidate)

        # Boost explicitly cited standards to the top
        norm = is_code.replace(" ", "").replace(":", "").upper()
        is_explicitly_cited = bool(norm and norm in explicit_codes)
        if is_explicitly_cited:
            score *= 0.2

        compliance = compliance_results.get(idx, {
            "is_code": is_code, "status": "unknown",
            "passed_fields": [], "failed_fields": [], "missing_fields": [],
            "mandatory_failed_fields": [], "advisory_failed_fields": [],
            "is_mandatory_compliant": None,
        })

        # Keyword overlap between standard text and tender spec
        std_text  = (candidate.get("title", "") + " " + candidate.get("description", "")).lower()
        std_words = set(re.findall(r'\b[a-z0-9]{3,}\b', std_text))
        matched_terms = [
            w for w in std_words
            if w not in stopwords and re.search(r'\b' + re.escape(w) + r'\b', spec_text_lower)
        ]

        entry = dict(candidate)
        entry.update({
            "is_code":                  is_code,
            "title":                    title,
            "semantic_score":           score,
            "explicitly_cited":         is_explicitly_cited,
            "matched_terms":            matched_terms,
            "compliance_status":        compliance["status"],
            "passed_fields":            compliance["passed_fields"],
            "failed_fields":            compliance["failed_fields"],
            "missing_fields":           compliance["missing_fields"],
            "mandatory_failed_fields":  compliance.get("mandatory_failed_fields", []),
            "advisory_failed_fields":   compliance.get("advisory_failed_fields", []),
            "is_mandatory_compliant":   compliance.get("is_mandatory_compliant"),
            "_tier":                    _COMPLIANCE_TIER.get(compliance["status"], _DEFAULT_TIER),
        })
        enriched.append(entry)

    # ── 6. Sort: tier ASC, then semantic score ASC ───────────────────────────
    enriched.sort(key=lambda item: (item["_tier"], item["semantic_score"]))

    # ── 7. Strip internal sort key ───────────────────────────────────────────
    all_ranked = [{k: v for k, v in e.items() if k != "_tier"} for e in enriched]

    # ── 8. Split into recommendations + also_considered ──────────────────────
    recommendations = all_ranked[:5]
    runner_ups      = all_ranked[5:8]

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
            "title":   entry.get("title", ""),
            "reason":  reason,
        })

    return {
        "spec_id":          spec_id,
        "spec_text":        spec_text,
        "recommendations":  recommendations,
        "also_considered":  also_considered,
    }


# Backwards compatibility alias
rank_results = rank_recommendations
