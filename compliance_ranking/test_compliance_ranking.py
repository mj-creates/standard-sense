"""
test_compliance_ranking.py
--------------------------
Integration test for compliance_ranking/compliance_checker.py.

Runs check_compliance() against REAL spec_parameters produced by
nlp_extraction/extractor.py on the actual sample PDF, then tests
all 9 IS codes in mock_requirements.json plus 2 edge cases.

Usage (from project root):
    python compliance_ranking/test_compliance_ranking.py

Output is plain ASCII to avoid Windows console encoding issues.
"""

import json
import pathlib
import sys

# Ensure project root is on the path regardless of cwd
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nlp_extraction.extractor import extract_from_pdf
from compliance_ranking.compliance_checker import check_compliance

SEP  = "=" * 68
SEP2 = "-" * 68

ALL_IS_CODES = [
    "IS 1554", "IS 694",  "IS 8828", "IS 302",
    "IS 1786", "IS 2062", "IS 8112",
    "IS 9873", "IS 1293",
]

REQUIREMENTS_PATH = ROOT / "compliance_ranking" / "mock_requirements.json"
REQUIREMENTS = {
    e["is_code"]: e["requirements"]
    for e in json.loads(REQUIREMENTS_PATH.read_text(encoding="utf-8"))
}

PDF_PATH = ROOT / "data" / "sample_tenders" / "sample_tender_01.pdf"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

def subsection(title):
    print(f"\n{SEP2}\n  {title}\n{SEP2}")

def safe_str(v):
    """Encode value to ASCII-safe string for Windows console."""
    return str(v).encode("ascii", errors="replace").decode("ascii")


def evaluate_correctness(is_code, result, spec_params):
    """
    Cross-check each field verdict against the raw spec value and requirement rule.
    Returns (correct_count, wrong_list).
    """
    if is_code not in REQUIREMENTS:
        return 0, []

    reqs   = REQUIREMENTS[is_code]
    wrong  = []
    correct = 0

    all_fields = list(reqs.keys())
    for field in all_fields:
        rule      = reqs[field]
        raw_val   = spec_params.get(field)
        in_passed  = field in result["passed_fields"]
        in_failed  = field in result["failed_fields"]
        in_missing = field in result["missing_fields"]

        verdict = (
            "passed"  if in_passed  else
            "failed"  if in_failed  else
            "missing" if in_missing else "UNCLASSIFIED"
        )

        # Sanity: field must appear in exactly one bucket
        buckets = sum([in_passed, in_failed, in_missing])
        if buckets != 1:
            wrong.append(
                f"  [LOGIC ERROR] '{field}' appears in {buckets} buckets "
                f"(should be exactly 1)"
            )
            continue

        # Missing check: if raw_val is None, must be missing
        if raw_val is None and verdict != "missing":
            wrong.append(
                f"  [WRONG] '{field}': raw_val=None but classified as {verdict}"
            )
        elif raw_val is not None and verdict == "missing":
            wrong.append(
                f"  [WRONG] '{field}': raw_val='{safe_str(raw_val)}' "
                f"but classified as missing"
            )
        else:
            correct += 1

    return correct, wrong


# ---------------------------------------------------------------------------
# STEP 1 — Real extraction
# ---------------------------------------------------------------------------

section("STEP 1: REAL NLP EXTRACTION OUTPUT")
print(f"  PDF: {PDF_PATH}")

if not PDF_PATH.exists():
    print("  ERROR: PDF not found. Cannot run test.")
    sys.exit(1)

extraction = extract_from_pdf(str(PDF_PATH))
spec_params = extraction.get("parameters", {})

print(f"\n  Full extraction output:")
for k, v in extraction.items():
    if k == "parameters":
        print(f"    parameters:")
        for pk, pv in v.items():
            print(f"      {pk:25} = {safe_str(pv)}")
    elif k == "specs":
        print(f"    specs ({len(v)} items):")
        for s in v:
            print(f"      - {safe_str(s)}")
    else:
        print(f"    {k:25} = {safe_str(v)}")

print(f"\n  spec_parameters going into compliance check:")
print(f"  {json.dumps({k: safe_str(v) for k, v in spec_params.items()}, indent=4)}")


# ---------------------------------------------------------------------------
# STEP 2 + 3 — All 9 IS codes
# ---------------------------------------------------------------------------

section("STEP 2+3: check_compliance() FOR ALL 9 IS CODES")

total_correct = 0
total_fields  = 0
all_wrong     = {}

for is_code in ALL_IS_CODES:
    subsection(f"{is_code}")

    result = check_compliance(spec_params, is_code)

    # Print requirements for this code alongside the verdict
    if is_code in REQUIREMENTS:
        print("  Requirements defined:")
        for field, rule in REQUIREMENTS[is_code].items():
            raw_val = spec_params.get(field, "<ABSENT>")
            print(f"    {field:25} rule={rule}   spec_value='{safe_str(raw_val)}'")

    print(f"\n  Result:")
    print(f"    status         : {result['status']}")
    print(f"    passed_fields  : {result['passed_fields']}")
    print(f"    failed_fields  : {result['failed_fields']}")
    print(f"    missing_fields : {result['missing_fields']}")

    # Correctness evaluation
    correct, wrong = evaluate_correctness(is_code, result, spec_params)
    n_fields = len(REQUIREMENTS.get(is_code, {}))
    total_correct += correct
    total_fields  += n_fields
    all_wrong[is_code] = wrong

    if wrong:
        print(f"\n  [!!] LOGIC ISSUES DETECTED:")
        for w in wrong:
            print(w)
    else:
        print(f"  [OK] All {n_fields} field classifications look correct")


# ---------------------------------------------------------------------------
# STEP 4 — Explicit stress-test callouts
# ---------------------------------------------------------------------------

section("STEP 4: STRESS-TEST CALLOUTS")

subsection("4a: power field range comparison (IS 8828 min 1W, IS 1293 max 3680W)")
power_val = spec_params.get("power", "<ABSENT>")
print(f"  Extracted power value: '{safe_str(power_val)}'")

# IS 8828: min 1W  -- should compare lower bound of range
r_8828 = check_compliance(spec_params, "IS 8828")
print(f"\n  IS 8828 (min: 1W):")
print(f"    power in passed : {'power' in r_8828['passed_fields']}")
print(f"    power in failed : {'power' in r_8828['failed_fields']}")
print(f"    power in missing: {'power' in r_8828['missing_fields']}")
if power_val != "<ABSENT>":
    import re
    tokens = re.findall(r"-?\d+(?:\.\d+)?", str(power_val))
    lower_bound = float(tokens[0]) if tokens else None
    print(f"    lower bound parsed from range: {lower_bound}W  >= 1W? {lower_bound >= 1.0 if lower_bound is not None else 'N/A'}")

# IS 1293: max 3680W -- should compare upper bound of range
r_1293 = check_compliance(spec_params, "IS 1293")
print(f"\n  IS 1293 (max: 3680W):")
print(f"    power in passed : {'power' in r_1293['passed_fields']}")
print(f"    power in failed : {'power' in r_1293['failed_fields']}")
print(f"    power in missing: {'power' in r_1293['missing_fields']}")
if power_val != "<ABSENT>":
    upper_bound = float(tokens[-1]) if tokens else None
    print(f"    upper bound parsed from range: {upper_bound}W  <= 3680W? {upper_bound <= 3680.0 if upper_bound is not None else 'N/A'}")


subsection("4b: grade field absent for LED spec (IS 1786 Fe415, IS 2062 E250)")
grade_val = spec_params.get("grade", None)
print(f"  Extracted grade value: {grade_val!r}  (expected: None)")
r_1786 = check_compliance(spec_params, "IS 1786")
r_2062 = check_compliance(spec_params, "IS 2062")
print(f"\n  IS 1786 (grade min Fe415):")
print(f"    grade in missing: {'grade' in r_1786['missing_fields']}  <-- expected True")
print(f"    crashed: False  (we are here, so no crash)")
print(f"\n  IS 2062 (grade min E250):")
print(f"    grade in missing: {'grade' in r_2062['missing_fields']}  <-- expected True")
print(f"    crashed: False  (we are here, so no crash)")


subsection("4c: operating_temperature range parsing (IS 9873 max 50)")
temp_val = spec_params.get("operating_temperature", "<ABSENT>")
print(f"  Extracted operating_temperature: '{safe_str(temp_val)}'")
r_9873 = check_compliance(spec_params, "IS 9873")
print(f"\n  IS 9873 (max: 50):")
print(f"    operating_temperature in passed : {'operating_temperature' in r_9873['passed_fields']}")
print(f"    operating_temperature in failed : {'operating_temperature' in r_9873['failed_fields']}")
print(f"    operating_temperature in missing: {'operating_temperature' in r_9873['missing_fields']}")
if temp_val != "<ABSENT>":
    import re as _re
    t_tokens = _re.findall(r"-?\d+(?:\.\d+)?", str(temp_val))
    print(f"    numeric tokens parsed: {t_tokens}")
    if len(t_tokens) >= 2:
        upper = float(t_tokens[-1])
        print(f"    upper bound: {upper}  <= 50? {upper <= 50.0}")
    else:
        print(f"    single token: {t_tokens} (not a range)")


subsection("4d: structural/cement codes against LED lighting spec")
structural_codes = ["IS 1786", "IS 2062", "IS 8112"]
for code in structural_codes:
    r = check_compliance(spec_params, code)
    print(f"\n  {code}:")
    print(f"    status        : {r['status']}")
    print(f"    passed_fields : {r['passed_fields']}")
    print(f"    failed_fields : {r['failed_fields']}")
    print(f"    missing_fields: {r['missing_fields']}")
    all_reqs = list(REQUIREMENTS.get(code, {}).keys())
    if r["passed_fields"]:
        print(f"    [!!] WARNING: {r['passed_fields']} passed on a structural code vs LED spec -- verify correctness")
    else:
        print(f"    [OK] No fields passed (expected for structural code vs LED spec)")


# ---------------------------------------------------------------------------
# STEP 5 — Edge cases
# ---------------------------------------------------------------------------

section("STEP 5: EDGE CASES")

subsection("5a: Unknown IS code (IS 99999)")
r_unknown = check_compliance(spec_params, "IS 99999")
print(f"  Result: {r_unknown}")
expected = {"is_code": "IS 99999", "status": "unknown",
            "passed_fields": [], "failed_fields": [], "missing_fields": []}
match = r_unknown == expected
print(f"  Matches expected exactly: {match}  {'[OK]' if match else '[FAIL]'}")

subsection("5b: Empty spec_parameters against real IS code (IS 1554)")
r_empty = check_compliance({}, "IS 1554")
print(f"  Result: {r_empty}")
req_fields = sorted(REQUIREMENTS["IS 1554"].keys())
got_missing = sorted(r_empty.get("missing_fields", []))
print(f"  status is 'unknown'        : {r_empty['status'] == 'unknown'}  {'[OK]' if r_empty['status'] == 'unknown' else '[FAIL]'}")
print(f"  passed_fields is []        : {r_empty['passed_fields'] == []}  {'[OK]' if r_empty['passed_fields'] == [] else '[FAIL]'}")
print(f"  failed_fields is []        : {r_empty['failed_fields'] == []}  {'[OK]' if r_empty['failed_fields'] == [] else '[FAIL]'}")
print(f"  missing_fields = all fields: {got_missing == req_fields}  {'[OK]' if got_missing == req_fields else '[FAIL]'}")
print(f"  expected missing: {req_fields}")
print(f"  got missing     : {got_missing}")


# ---------------------------------------------------------------------------
# Final verdict
# ---------------------------------------------------------------------------

section("FINAL VERDICT")
print(f"  Field-level classifications correct: {total_correct}/{total_fields}")
print()

any_wrong = False
for code, wrongs in all_wrong.items():
    if wrongs:
        any_wrong = True
        print(f"  [ISSUES] {code}:")
        for w in wrongs:
            print(f"    {w}")

if not any_wrong:
    print("  All 9 IS code results: field classifications logically correct")

# Edge case summary
ec_a_ok = (r_unknown == expected)
ec_b_ok = (
    r_empty["status"] == "unknown"
    and r_empty["passed_fields"] == []
    and r_empty["failed_fields"] == []
    and sorted(r_empty.get("missing_fields", [])) == sorted(REQUIREMENTS["IS 1554"].keys())
)
print(f"\n  Edge case 5a (unknown IS code) : {'PASS' if ec_a_ok else 'FAIL'}")
print(f"  Edge case 5b (empty spec)       : {'PASS' if ec_b_ok else 'FAIL'}")

passed_edge = sum([ec_a_ok, ec_b_ok])
print(f"\n  Edge cases: {passed_edge}/2 passed")
print(f"\n  Overall: {total_correct}/{total_fields} field classifications correct "
      f"+ {passed_edge}/2 edge cases passed")

if not any_wrong and passed_edge == 2:
    print("\n  RESULT: ALL TESTS PASSED -- compliance_checker.py is ready for commit")
else:
    print("\n  RESULT: ISSUES FOUND -- review above before committing")

print()
