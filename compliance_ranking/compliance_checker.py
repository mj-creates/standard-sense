"""
compliance_checker.py
---------------------
Checks whether extracted tender spec parameters satisfy the mandatory
technical requirements defined for a given IS code.

Loaded by the compliance-ranking pipeline; designed to be called once
per (spec, IS code) pair returned by semantic search.

Public API
----------
check_compliance(spec_parameters: dict, is_code: str) -> dict

Return shape:
    {
        "is_code":         str,
        "status":          "compliant" | "partial" | "non-compliant" | "unknown",
        "passed_fields":   list[str],
        "failed_fields":   list[str],
        "missing_fields":  list[str],
    }
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

# ---------------------------------------------------------------------------
# Module-level data load  (cached; no file I/O per call)
# ---------------------------------------------------------------------------

_REQUIREMENTS_PATH = pathlib.Path(__file__).parent / "mock_requirements.json"

def _load_requirements() -> dict[str, dict]:
    """Return {is_code: requirements_dict} mapping from mock_requirements.json."""
    raw = json.loads(_REQUIREMENTS_PATH.read_text(encoding="utf-8"))
    return {entry["is_code"]: entry["requirements"] for entry in raw}

_REQUIREMENTS: dict[str, dict] = _load_requirements()


def _is_mandatory(rule: dict) -> bool:
    """
    Return True if the requirement rule is flagged as mandatory.

    Rules that carry  "mandatory": true  are hard safety/statutory
    requirements — a spec that fails them is non-compliant for the
    purposes of the rule filter.

    Rules that carry  "mandatory": false  (or omit the flag, defaulting
    to True for backwards compatibility with legacy entries) are advisory
    best-practice recommendations — failing them reduces the compliance
    score but does not disqualify the spec outright.

    Default is True so that any legacy rule without a mandatory key
    continues to behave as a hard requirement.
    """
    return bool(rule.get("mandatory", True))


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _extract_numeric(value: str) -> float | None:
    """
    Pull the first numeric token (int or float) out of a string,
    applying SI unit scaling so comparisons are always in base units.

    Scaling rules applied when a SI-prefix unit follows the number:
        kV  → multiply by 1000   ("0.23 kV" → 230.0)
        kW  → multiply by 1000   ("25 kW"   → 25000.0)
        MW  → multiply by 1e6
        MV  → multiply by 1e6

    Examples:
        "230V AC"    -> 230.0
        "0.23 kV"    -> 230.0   (scaled from kV)
        "IP65"       -> 65.0
        "Fe500"      -> 500.0
        "3680W"      -> 3680.0
        "25 kW"      -> 25000.0  (scaled from kW)
        "50000 hrs"  -> 50000.0
        "0.23 kV"    -> 230.0   (scaled from kV)
        "25 kW"      -> 25000.0  (scaled from kW)
    """
    match = re.search(r"[-+]?\d+(?:\.\d+)?", value)
    if not match:
        return None
    num = float(match.group())

    # Apply SI prefix scaling when the unit immediately follows the number
    suffix_match = re.search(r"\d\s*(kV|kW|MW|MV)\b", value, re.IGNORECASE)
    if suffix_match:
        suffix = suffix_match.group(1).lower()
        multipliers = {"kv": 1_000, "kw": 1_000, "mv": 1_000_000, "mw": 1_000_000}
        num *= multipliers.get(suffix, 1)

    return num


def _extract_range(value: str) -> tuple[float, float] | None:
    """
    Parse a range expression like "100-150W", "220-240V", "-10 deg C to 50 deg C"
    into (lower, upper) floats.

    Returns None if the value does not look like a range (single value).

    Fix for range-separator vs negative-sign ambiguity
    ---------------------------------------------------
    The naive regex  r"-?\\d+(?:\\.\\d+)?"  greedily treats the hyphen in
    "100-150W" as a negative sign on 150, producing tokens [100, -150].

    Corrected approach: a "-" is treated as a negative sign ONLY when it is
    NOT immediately preceded by a digit.  Negative lookbehind (?<!\\d) enforces
    this at match time.

    Walkthrough with the fixed regex  r"(?<!\\d)-?\\d+(?:\\.\\d+)?":

        "100-150W"        hyphen is preceded by '0' (a digit)
                          lookbehind FAILS -> hyphen not captured
                          tokens: ['100', '150']          (100.0, 150.0)  CORRECT

        "-10 deg C to 50" leading '-' at position 0, not preceded by any digit
                          lookbehind PASSES -> '-' captured as negative sign
                          tokens: ['-10', '50']            (-10.0, 50.0)  CORRECT

        "220-240V"        same as first case
                          tokens: ['220', '240']           (220.0, 240.0) CORRECT

        "230V AC"         only one token found -> returns None             CORRECT
    """
    tokens = re.findall(r"(?<!\d)-?\d+(?:\.\d+)?", value)
    if len(tokens) >= 2:
        return float(tokens[0]), float(tokens[-1])
    return None


def _extract_ip_number(value: str) -> int | None:
    """
    Extract the two-digit integer from an IP rating string.

    "IP65" -> 65,  "IP 44" -> 44,  "ip20" -> 20
    Returns None on parse failure.

    Approximation used (documented in prompt spec):
        IP ratings are compared as plain two-digit integers.
        Higher number = better protection for common procurement checks.
        This is a hackathon-level approximation; full IEC 60529 comparison
        would require separate digit-by-digit analysis.
    """
    match = re.search(r"[Ii][Pp]\s*(\d{2})", value)
    if match:
        return int(match.group(1))
    # Fallback: bare two-digit number (e.g. "65")
    match = re.search(r"\b(\d{2})\b", value)
    if match:
        return int(match.group(1))
    return None


def _extract_grade_number(value: str) -> tuple[str, float] | None:
    """
    Parse a grade string into (prefix, numeric_part).

    Supported formats:
        "Fe415"  -> ("FE", 415.0)
        "Fe 500D" -> ("FE", 500.0)
        "E250"   -> ("E",  250.0)
        "43"     -> ("",   43.0)
        "M 25"   -> ("M",  25.0)

    Returns None on parse failure.
    """
    v = value.strip()

    # Matches optional prefix letters (and spaces/hyphens), followed by digits
    match = re.search(r"^([A-Za-z]+(?:[\s\-]*[A-Za-z]+)*)?\s*(\d+(?:\.\d+)?)", v, re.IGNORECASE)
    if match:
        prefix = match.group(1).upper() if match.group(1) else ""
        prefix = prefix.replace(" ", "").replace("-", "")
        number = float(match.group(2))
        return prefix, number

    return None


# ---------------------------------------------------------------------------
# Per-field comparison helpers
# (each returns True = pass, False = fail, None = parse error)
# ---------------------------------------------------------------------------

def _check_required_present(spec_value: str) -> bool:
    """Pass if the value is a non-empty, non-whitespace string."""
    return bool(spec_value and spec_value.strip())


def _compare_ip_rating(spec_value: str, rule: dict) -> bool | None:
    """
    Compare an IP-rated protection field.

    Supports {"min": "IP##"} and {"max": "IP##"} rules.
    Returns None on parse failure of either side.
    """
    spec_ip = _extract_ip_number(spec_value)
    req_value = rule.get("min") or rule.get("max")
    if req_value is None:
        return None
    req_ip = _extract_ip_number(str(req_value))

    if spec_ip is None or req_ip is None:
        return None  # parse failure -> caller marks as failed

    if "min" in rule:
        return spec_ip >= req_ip
    # max (uncommon for IP, but handle it)
    return spec_ip <= req_ip


def _compare_grade(spec_value: str, rule: dict) -> bool | None:
    """
    Compare grade strings like "Fe415", "E250", "43".

    Cross-prefix mismatches (e.g. Fe spec vs E requirement) are treated as
    parse failures (returns None) rather than hard fails, because the spec
    and the requirement are from incompatible grade families.

    Supports {"min": "..."} rules.
    """
    req_raw = rule.get("min") or rule.get("max")
    if req_raw is None:
        return None

    spec_parsed = _extract_grade_number(str(spec_value))
    req_parsed  = _extract_grade_number(str(req_raw))

    if spec_parsed is None or req_parsed is None:
        return None

    spec_prefix, spec_num = spec_parsed
    req_prefix,  req_num  = req_parsed

    # Enforce same prefix family
    if spec_prefix.upper() != req_prefix.upper():
        # Cross-family: treat as parse/classification mismatch, not a numeric fail
        return None

    if "min" in rule:
        return spec_num >= req_num
    return spec_num <= req_num


def _compare_numeric_with_unit(
    spec_value: str,
    rule: dict,
    field_name: str,
) -> bool | None:
    """
    Generic numeric comparison for fields that carry a unit suffix
    (voltage, power, operating_temperature, lifespan, etc.).

    Range spec values (e.g. "100-150W", "220-240V", "-10 deg C to 50 deg C"):
        For a MAX requirement -> compare the range's UPPER bound against the limit.
        For a MIN requirement -> compare the range's LOWER bound against the limit.

        Rationale: for a max limit we care about the worst case (highest the
        spec could reach); for a min limit we care about the guaranteed baseline
        (lowest the spec commits to).  Using the other bound in each case would
        allow specs to slip through that should be rejected (max case) or be
        wrongly rejected (min case).

    Single spec values (e.g. "230V AC", "3680W"):
        Extract the leading numeric token and compare directly.

    Returns None on parse failure.
    """
    req_raw = rule.get("min") or rule.get("max")
    if req_raw is None:
        return None

    req_num = _extract_numeric(str(req_raw))
    if req_num is None:
        # Fallback for non-numeric categorical requirements
        return str(spec_value).strip().lower() == str(req_raw).strip().lower()

    # Attempt range parse first
    range_result = _extract_range(str(spec_value))
    if range_result is not None:
        lower, upper = range_result
        if "max" in rule:
            spec_num = upper    # worst case for an upper-bound check
        else:
            spec_num = lower    # guaranteed baseline for a lower-bound check
    else:
        spec_num = _extract_numeric(str(spec_value))
        if spec_num is None:
            return None

    if "max" in rule:
        return spec_num <= req_num
    return spec_num >= req_num


# ---------------------------------------------------------------------------
# Field dispatcher
# ---------------------------------------------------------------------------

def _evaluate_field(
    field: str,
    rule: dict,
    spec_value: str | None,
) -> bool | None:
    """
    Route a single field to the correct comparison helper.

    Returns:
        True  -- requirement satisfied
        False -- requirement violated
        None  -- parse failure (value present but unusable)
    """
    if rule.get("required") is True:
        return _check_required_present(spec_value or "")

    if field == "protection":
        return _compare_ip_rating(spec_value or "", rule)

    if field == "grade":
        return _compare_grade(spec_value or "", rule)

    # All other numeric+unit fields (voltage, power, operating_temperature, lifespan, etc.)
    return _compare_numeric_with_unit(spec_value or "", rule, field)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_compliance(
    spec_parameters: dict[str, Any],
    is_code: str,
) -> dict:
    """
    Check whether spec_parameters satisfies the requirements defined for
    is_code in mock_requirements.json.

    Each requirement rule carries an optional "mandatory" boolean flag:
      - mandatory: true  (default) → hard statutory/safety requirement.
                                     Failing it → appears in failed_fields
                                     AND mandatory_failed_fields.
      - mandatory: false           → advisory best-practice requirement.
                                     Failing it → appears in failed_fields
                                     AND advisory_failed_fields (not in
                                     mandatory_failed_fields).

    Parameters
    ----------
    spec_parameters : dict
        The "parameters" dict produced by nlp_extraction/extractor.py.
        Keys are field names like "voltage", "protection", "grade", etc.
        Values are raw strings as extracted from the tender document.
    is_code : str
        The IS code to check against (e.g. "IS 1554").

    Returns
    -------
    dict with keys:
        is_code                 str
        status                  "compliant" | "partial" | "non-compliant" | "unknown"
        passed_fields           list[str]   — all fields that passed
        failed_fields           list[str]   — ALL fields that failed (mandatory + advisory)
        missing_fields          list[str]   — fields absent from spec
        mandatory_failed_fields list[str]   — subset of failed_fields: mandatory-only failures
        advisory_failed_fields  list[str]   — subset of failed_fields: advisory-only failures
        is_mandatory_compliant  bool        — True iff zero mandatory fields failed/missing
    """
    _UNKNOWN = {
        "is_code":                  is_code,
        "status":                   "unknown",
        "passed_fields":            [],
        "failed_fields":            [],
        "missing_fields":           [],
        "mandatory_failed_fields":  [],
        "advisory_failed_fields":   [],
        "is_mandatory_compliant":   False,
    }

    # No entry in requirements data
    if is_code not in _REQUIREMENTS:
        return _UNKNOWN

    requirements = _REQUIREMENTS[is_code]

    # Empty or None spec
    if not spec_parameters:
        mandatory_missing = [f for f, r in requirements.items() if _is_mandatory(r)]
        return {
            **_UNKNOWN,
            "status":         "unknown",
            "missing_fields": list(requirements.keys()),
            "mandatory_failed_fields": mandatory_missing,
            "is_mandatory_compliant":  False,
        }

    passed:             list[str] = []
    failed:             list[str] = []
    missing:            list[str] = []
    mandatory_failed:   list[str] = []
    advisory_failed:    list[str] = []

    for field, rule in requirements.items():
        raw_value  = spec_parameters.get(field)
        is_mand    = _is_mandatory(rule)

        # Field completely absent from extracted parameters
        if raw_value is None:
            missing.append(field)
            # A missing mandatory field counts as a mandatory failure for
            # the is_mandatory_compliant flag, but not in mandatory_failed_fields
            # (missing is its own category — the caller can check both lists)
            continue

        result = _evaluate_field(field, rule, str(raw_value))

        if result is True:
            passed.append(field)
        else:
            # result is False (explicit fail) or None (parse error → treat as fail)
            failed.append(field)
            if is_mand:
                mandatory_failed.append(field)
            else:
                advisory_failed.append(field)

    # is_mandatory_compliant: True only if no mandatory field failed OR is missing
    mandatory_missing = [f for f in missing if _is_mandatory(requirements[f])]
    is_mandatory_compliant = (len(mandatory_failed) == 0 and len(mandatory_missing) == 0)

    # Compute overall status (unchanged semantics — backward compatible)
    if not failed and not missing:
        status = "compliant"
    elif passed and (failed or missing):
        status = "partial"
    else:
        status = "non-compliant"

    return {
        "is_code":                  is_code,
        "status":                   status,
        "passed_fields":            passed,
        "failed_fields":            failed,
        "missing_fields":           missing,
        "mandatory_failed_fields":  mandatory_failed,
        "advisory_failed_fields":   advisory_failed,
        "is_mandatory_compliant":   is_mandatory_compliant,
    }
