"""
llm_compliance.py
-----------------
Dynamic LLM-based compliance checking for IS standards that are not covered
by the hand-written rules in mock_requirements.json.

For any candidate NOT in the legacy _REQUIREMENTS dict, this module:
  1. Builds a structured Groq prompt with the standard's title/description
     and the tender's extracted spec_parameters.
  2. Asks the LLM to infer the standard's likely field-level requirements and
     compare them against the provided parameters.
  3. Returns a compliance dict in the same shape as check_compliance().

Public API
----------
extract_and_check_compliance_llm(
    spec_parameters: dict,
    is_code: str,
    title: str,
    description: str,
) -> dict

The function NEVER raises — any failure returns the neutral "unknown" fallback.
Results are cached in-memory per (is_code, frozen spec_parameters) pair.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Neutral fallback — identical shape to check_compliance() "unknown" return
# ---------------------------------------------------------------------------
def _unknown(is_code: str) -> dict:
    return {
        "is_code":                  is_code,
        "status":                   "unknown",
        "passed_fields":            [],
        "failed_fields":            [],
        "missing_fields":           [],
        "mandatory_failed_fields":  [],
        "advisory_failed_fields":   [],
        "is_mandatory_compliant":   None,
    }


# ---------------------------------------------------------------------------
# In-memory result cache keyed by (is_code, frozenset of spec_params items)
# Prevents redundant LLM calls when the same standard appears across uploads
# during the same server session.
# ---------------------------------------------------------------------------
_llm_cache: dict[tuple, dict] = {}


def _cache_key(is_code: str, spec_parameters: dict) -> tuple:
    """Stable, hashable cache key for a (standard, spec) pair."""
    try:
        params_key = frozenset(
            (k, str(v)) for k, v in sorted(spec_parameters.items())
        )
    except Exception:
        params_key = frozenset()
    return (is_code, params_key)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
def _build_prompt(
    is_code: str,
    title: str,
    description: str,
    spec_parameters: dict,
) -> str:
    params_str = (
        json.dumps(spec_parameters, ensure_ascii=False, indent=2)
        if spec_parameters
        else "{}"
    )
    # Truncate description to avoid token bloat
    desc_truncated = (description or "")[:400].strip()

    return f"""You are a Bureau of Indian Standards (BIS) compliance expert.

Your task is to assess whether a procurement tender meets the requirements of a specific Indian Standard (IS code).

## Indian Standard Being Evaluated
- IS Code: {is_code}
- Title: {title}
- Description: {desc_truncated}

## Tender Specification Parameters (extracted from tender document)
{params_str}

## Instructions
1. Based on the standard's title and description, identify the key technical field requirements this standard typically mandates (e.g. voltage limits, material grades, IP ratings, certifications, dimensions, temperature ranges, etc.).
2. For each identified requirement field:
   - If the tender's parameters include a value for that field AND it appears to satisfy the standard's likely threshold → add to passed_fields.
   - If the tender's parameters include a value for that field BUT it appears to violate the standard's likely threshold → add to failed_fields.
   - If the tender's parameters do NOT include a value for that field at all → add to missing_fields.
3. Determine overall compliance status:
   - "compliant"     → all identified fields are in passed_fields
   - "partial"       → some fields passed, some failed or missing
   - "non-compliant" → most or all identified fields failed
4. Use "unknown" status ONLY if you cannot determine any meaningful requirements from the standard's title/description (e.g. the standard is purely procedural with no measurable parameters).

## Output Format
Respond with ONLY a valid JSON object. No extra text, no markdown fences.

{{
  "status": "compliant" | "partial" | "non-compliant" | "unknown",
  "passed_fields": ["field_name", ...],
  "failed_fields": ["field_name", ...],
  "missing_fields": ["field_name", ...],
  "reasoning": "one sentence summary of the compliance verdict"
}}"""


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------
def extract_and_check_compliance_llm(
    spec_parameters: dict[str, Any],
    is_code: str,
    title: str,
    description: str,
) -> dict:
    """
    Dynamically assess compliance using an LLM for standards not covered by
    the legacy mock_requirements.json rule set.

    Parameters
    ----------
    spec_parameters : dict
        Extracted tender parameters (from nlp_extraction/extractor.py).
    is_code : str
        The IS code (e.g. "IS/IEC 80601 (Part 2/Sec 49):2018").
    title : str
        Standard title from FAISS metadata / SQLite.
    description : str
        Standard description from FAISS metadata (may be empty).

    Returns
    -------
    dict
        Same shape as compliance_checker.check_compliance().
        NEVER raises — returns neutral "unknown" dict on any failure.
    """
    # Cache check
    key = _cache_key(is_code, spec_parameters or {})
    if key in _llm_cache:
        return _llm_cache[key]

    result = _unknown(is_code)

    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("GROQ_API_KEY not set — skipping LLM compliance check for %s", is_code)
            return result

        client = Groq(api_key=api_key)
        prompt = _build_prompt(is_code, title, description, spec_parameters or {})

        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a BIS compliance expert. "
                        "Output only valid JSON with the exact keys requested. "
                        "No markdown, no extra text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            timeout=8,          # hard cap — one slow call must not stall the demo
        )

        raw = response.choices[0].message.content
        if not raw:
            return result

        parsed: dict = json.loads(raw)

        # Validate and normalise the LLM output
        valid_statuses = {"compliant", "partial", "non-compliant", "unknown"}
        status = str(parsed.get("status", "unknown")).strip().lower()
        if status not in valid_statuses:
            status = "unknown"

        passed  = [str(f) for f in parsed.get("passed_fields",  []) if f]
        failed  = [str(f) for f in parsed.get("failed_fields",  []) if f]
        missing = [str(f) for f in parsed.get("missing_fields", []) if f]

        # Derive mandatory_failed_fields heuristic:
        # treat all failed fields as mandatory for unmapped standards
        # (conservative — better to flag too much than too little)
        mandatory_failed = list(failed)
        is_mandatory_compliant: bool | None = (
            len(mandatory_failed) == 0 and len(missing) == 0
            if status != "unknown"
            else None
        )

        result = {
            "is_code":                  is_code,
            "status":                   status,
            "passed_fields":            passed,
            "failed_fields":            failed,
            "missing_fields":           missing,
            "mandatory_failed_fields":  mandatory_failed,
            "advisory_failed_fields":   [],
            "is_mandatory_compliant":   is_mandatory_compliant,
        }

    except json.JSONDecodeError as exc:
        logger.warning(
            "LLM compliance JSON parse error for %s: %s", is_code, exc
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "LLM compliance check failed for %s: %s", is_code, exc
        )

    # Cache and return (even the fallback, to avoid hammering the API on repeated failures)
    _llm_cache[key] = result
    return result
