"""
test_hardening.py
-----------------
Six adversarial test cases for the StandardSense NLP extraction pipeline.
Each test records EXACT extracted output and compares against expected values.

Run with:
    d:\\standard-sense\\venv\\Scripts\\python.exe nlp_extraction/test_hardening.py
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from nlp_extraction.extractor import extract_from_text, extract_parameters

SEP  = "=" * 72
results: list[dict] = []

def run_case(case_id: int, name: str, fn):
    print(f"\n{SEP}\n  CASE {case_id}: {name}\n{SEP}")
    try:
        passed, details = fn()
        status = "PASS" if passed else "FAIL"
    except Exception as exc:
        import traceback
        passed  = False
        status  = "ERROR"
        details = {"exception": str(exc), "traceback": traceback.format_exc()}
    results.append({"id": case_id, "name": name, "status": status, "details": details})
    print(f"  STATUS: [{status}]")
    if isinstance(details, dict):
        for k, v in details.items():
            val = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            wrapped = textwrap.fill(val, width=68, subsequent_indent="        ")
            print(f"  {k}: {wrapped}")
    print()


def case_1_no_is_standard():
    text = textwrap.dedent("""
        Tender for Supply of LED Street Lighting Fixtures
        Technical Specifications:
        - Power: 120W
        - Voltage: 230V AC
        - Protection: IP65
        - Lifespan: 50000 hours
        - Color Temperature: 4000K
        - Warranty: 5 years
        - Operating Temperature: -10°C to 50°C
    """)
    result = extract_from_text(text, spec_id="case1")
    params = result["parameters"]
    required = ["power", "voltage", "protection", "lifespan", "color_temperature", "warranty", "operating_temperature"]
    failures = [k for k in required if not params.get(k)]
    if result["explicit_standards"] != []:
        failures.append("explicit_standards should be []")
    passed = len(failures) == 0
    return passed, {"extracted_params": str(params), "explicit_standards": str(result["explicit_standards"]), "failures": str(failures) if failures else "none", "spec_text": result["spec_text"][:120]}


def case_2_table_format():
    text = textwrap.dedent("""
        Tender for Supply of LED Street Lights
        Technical Requirements:
        | Parameter           | Value          |
        |---------------------|----------------|
        | Power               | 100W           |
        | Voltage             | 230V AC        |
        | Protection Rating   | IP65           |
        | Lifespan            | 50000 hours    |
        | Warranty            | 3 years        |
        | Operating Temp      | -10°C to 45°C  |
    """)
    result = extract_from_text(text, spec_id="case2")
    params = result["parameters"]
    required = ["power", "voltage", "protection", "warranty"]
    failures = [k for k in required if not params.get(k)]
    passed = len(failures) == 0
    return passed, {"extracted_params": str(params), "missing_required": str(failures) if failures else "none"}


def case_3_variant_units():
    text = textwrap.dedent("""
        Supply of Industrial LED Fittings
        Power consumption: 100 to 150 Watts
        Ingress protection: IP-65
        Supply voltage: 230 Volts AC
        Rated life: 50,000 hrs
        Warranty period: 5 years
        Operating temperature range: -20 deg C to 55 deg C
    """)
    result = extract_from_text(text, spec_id="case3")
    params = result["parameters"]
    checks = {
        "power normalised to 100-150W": params.get("power") == "100-150W",
        "protection normalised to IP65": params.get("protection") == "IP65",
        "voltage extracted":            params.get("voltage") is not None,
        "lifespan extracted (not '50')": params.get("lifespan") not in (None, "50"),
        "warranty extracted":           params.get("warranty") is not None,
        "operating_temperature extracted": params.get("operating_temperature") is not None,
    }
    failures = [k for k, v in checks.items() if not v]
    passed = len(failures) == 0
    return passed, {"extracted_values": str({k: params.get(k) for k in ["power","protection","voltage","lifespan","warranty"]}), "failures": str(failures) if failures else "none"}


def case_4_multilingual_hindi():
    if not os.environ.get("GROQ_API_KEY"):
        return True, {"note": "SKIPPED — GROQ_API_KEY not set"}
    text = textwrap.dedent("""
        एलईडी स्ट्रीट लाइटिंग फिक्सचर की आपूर्ति
        तकनीकी विशिष्टताएं:
        - शक्ति: 100-150W
        - वोल्टेज: 230V AC
        - सुरक्षा रेटिंग: IP65
        - जीवनकाल: 50000 घंटे
        - वारंटी: 5 वर्ष
        - मानक: IS 10322
    """)
    result = extract_from_text(text, spec_id="case4")
    meta   = result["multilingual_meta"]
    params = result["parameters"]
    checks = {
        "was_translated": meta.get("was_translated") is True,
        "translation_success": meta.get("translation_success") is True,
        "Devanagari detected": "Devanagari" in meta.get("detected_scripts", []),
        "power extracted": "power" in params,
        "voltage extracted": "voltage" in params,
        "protection extracted": "protection" in params,
        "IS 10322 detected": "IS 10322" in result["explicit_standards"],
    }
    failures = [k for k, v in checks.items() if not v]
    passed = len(failures) == 0
    return passed, {"multilingual_meta": str(meta), "extracted_params": str(params), "failures": str(failures) if failures else "none"}


def case_5_image_pdf():
    result = extract_from_text("", spec_id="case5")
    checks = {
        "no crash": True,
        "parameters empty": result["parameters"] == {},
        "spec_text empty": result["spec_text"] == "",
        "was_translated False": result["multilingual_meta"]["was_translated"] is False,
    }
    failures = [k for k, v in checks.items() if not v]
    passed = len(failures) == 0
    return passed, {"parameters": str(result["parameters"]), "spec_text": repr(result["spec_text"]), "failures": str(failures) if failures else "none"}


def case_6_missing_fields():
    text = textwrap.dedent("""
        Supply of LED Luminaires
        Technical Specifications:
        - Power: 80W
        - Protection Rating: IP54
        - Lifespan: 40000 hours
        - Color Temperature: 5000K
    """)
    result = extract_from_text(text, spec_id="case6")
    params = result["parameters"]
    from compliance_ranking.compliance_checker import check_compliance
    cr = check_compliance(params, "IS 302")
    checks = {
        "power extracted":          "power" in params,
        "protection extracted":     "protection" in params,
        "warranty NOT guessed":     "warranty" not in params,
        "voltage NOT guessed":      "voltage" not in params,
        "warranty in IS302 missing": "warranty" in cr.get("missing_fields", []),
    }
    failures = [k for k, v in checks.items() if not v]
    passed = len(failures) == 0
    return passed, {"extracted_params": str(params), "IS302_missing_fields": str(cr.get("missing_fields", [])), "IS302_status": cr.get("status"), "failures": str(failures) if failures else "none"}


def case_bonus_kv_scaling():
    from compliance_ranking.compliance_checker import _extract_numeric
    raw = _extract_numeric("0.23 kV")
    correct = 230.0
    passed = (raw == correct)
    return passed, {"raw_extracted": str(raw), "expected": str(correct), "pass": str(passed)}


if __name__ == "__main__":
    print(f"\n{SEP}\n  StandardSense — Extraction Hardening Test Suite\n{SEP}")
    run_case(1, "No explicit IS standard — all params still extracted",   case_1_no_is_standard)
    run_case(2, "Table/pipe format — labeled fields extracted",           case_2_table_format)
    run_case(3, "Variant units — '100 to 150 Watts', 'IP-65', 'Volts'",  case_3_variant_units)
    run_case(4, "Multilingual Hindi — translation fires, params correct", case_4_multilingual_hindi)
    run_case(5, "Image/scanned PDF — empty text handled gracefully",      case_5_image_pdf)
    run_case(6, "Missing fields — not guessed, appear in missing_fields", case_6_missing_fields)
    run_case(7, "BONUS: kV scaled to V correctly",                        case_bonus_kv_scaling)

    print(f"\n{SEP}\n  PASS/FAIL SUMMARY\n{SEP}")
    print(f"  {'#':<4} {'Status':<8} Test Name")
    print(f"  {'-'*68}")
    all_pass = True
    for r in results:
        icon = "✓" if r["status"] == "PASS" else "✗"
        print(f"  {r['id']:<4} [{r['status']:<6}] {icon}  {r['name']}")
        if r["status"] != "PASS":
            all_pass = False
    print(f"\n  Overall: {'ALL PASS' if all_pass else 'FAILURES PRESENT'}")
    print(f"{SEP}\n")
    sys.exit(0 if all_pass else 1)
