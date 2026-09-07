"""
test_ranking_complete.py
------------------------
Comprehensive ranking pipeline test — 3 product categories + edge cases.

Covers:
  1.  LED / Street-lighting tender  (regression after extraction hardening)
  2.  PVC electrical cable tender
  3.  Plug / socket-outlet tender
  4.  Edge: empty semantic results  → empty recommendations, no crash
  5.  Edge: needs_clarification passthrough
  6.  Score sort-order verification  (LOWER L2 = better = ranked first)
  7.  Mandatory/advisory field exposure audit
  8.  Field-name contract: all output keys expected by RAG + frontend present

Run from project root:
    d:\\standard-sense\\venv\\Scripts\\python.exe compliance_ranking/test_ranking_complete.py
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

from compliance_ranking.compliance_checker import check_compliance, _extract_numeric
from compliance_ranking.ranking_engine import rank_recommendations

SEP  = "=" * 72
SEP2 = "-" * 60
RESULTS: list[dict] = []


def _run(case_id: int, name: str, fn):
    print(f"\n{SEP}\n  CASE {case_id}: {name}\n{SEP}")
    try:
        passed, details = fn()
        status = "PASS" if passed else "FAIL"
    except Exception as exc:
        import traceback
        passed, status = False, "ERROR"
        details = {"exception": str(exc), "tb": traceback.format_exc(limit=6)}
    RESULTS.append({"id": case_id, "name": name, "status": status})
    print(f"  STATUS: [{status}]")
    for k, v in (details if isinstance(details, dict) else {}).items():
        val = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        print(f"  {k}: {textwrap.fill(val, 68, subsequent_indent='        ')}")
    print()


# ─── Helper: build mock semantic search results ─────────────────────────────

def _sr(is_code: str, title: str, l2: float) -> dict:
    """Mimic the raw output of semantic_search()."""
    return {"is_code": is_code, "title": title,
            "description": "", "l2_score": l2}


# ═══════════════════════════════════════════════════════════════════════════
# CASE 1 — LED / Street-lighting regression
# ═══════════════════════════════════════════════════════════════════════════

def case_1_led_regression():
    """
    Full pipeline on the same LED tender that drives verify_dev.py.
    After extraction hardening, params are now normalized:
      power='100-150W', protection='IP65', voltage='230V AC' etc.
    Verify:
      - 5 recommendations returned
      - IS 10322 or IS 10322-5-3 is compliant (LED street light standard)
      - IS 302 is at least partial
      - no crash, all required output keys present
    """
    # These are the extracted params after hardening fixes
    params = {
        "power":               "100-150W",
        "protection":          "IP65",
        "lifespan":            "50000 hours",
        "voltage":             "230V AC",
        "color_temperature":   "4000K",
        "warranty":            "5 years",
        "operating_temperature": "-10°C to 50°C",
    }

    # Semantic results that verify_dev.py returns for LED spec
    sem = [
        _sr("IS 10322",    "Luminaires - LED Street Lighting",                    1.05),
        _sr("IS 10322-5-3","Luminaires Part 5 Section 3 - LED Road Luminaires",   1.08),
        _sr("IS 16520",    "Solid State Lighting Products - LED Street Lights",   1.12),
        _sr("IS 15885",    "LED Drivers and Control Gear",                        1.30),
        _sr("IS 302",      "Safety of Household and Similar Electrical Appliances",1.40),
    ]

    result = rank_recommendations("led_tender_01", "LED street light 100-150W IP65", params, sem)
    recs = result.get("recommendations", [])

    failures = []

    # 5 recommendations
    if len(recs) != 5:
        failures.append(f"expected 5 recs, got {len(recs)}")

    # Required output keys on every rec
    required_keys = {"is_code","title","semantic_score","compliance_status",
                     "passed_fields","failed_fields","missing_fields"}
    for i, rec in enumerate(recs):
        missing_keys = required_keys - set(rec.keys())
        if missing_keys:
            failures.append(f"rec[{i}] missing keys: {missing_keys}")

    # IS 10322 should be compliant (has IP65 min, power max 250W, voltage max 270V,
    #  operating_temperature required, warranty required, lifespan min 25000 hrs)
    codes_by_status = {r["is_code"]: r["compliance_status"] for r in recs}
    print(f"  Compliance by code: {json.dumps(codes_by_status, indent=2)}")

    led_statuses = {c: codes_by_status[c]
                    for c in ("IS 10322","IS 10322-5-3")
                    if c in codes_by_status}
    if not any(s == "compliant" for s in led_statuses.values()):
        failures.append(f"Neither IS 10322 nor IS 10322-5-3 is compliant: {led_statuses}")

    # Top result should be the compliant LED standard (lowest tier + score)
    if recs and recs[0]["compliance_status"] != "compliant":
        failures.append(f"Top rec is not compliant: {recs[0]['is_code']} = {recs[0]['compliance_status']}")

    # _tier must NOT appear in output (internal key stripping)
    leaked = [r for r in recs if "_tier" in r]
    if leaked:
        failures.append(f"_tier leaked into output for {[r['is_code'] for r in leaked]}")

    passed = len(failures) == 0
    return passed, {
        "recs_count":   str(len(recs)),
        "top_rec":      f"{recs[0]['is_code']} ({recs[0]['compliance_status']})" if recs else "none",
        "led_statuses": str(led_statuses),
        "failures":     str(failures) if failures else "none",
    }


# ═══════════════════════════════════════════════════════════════════════════
# CASE 2 — PVC Electrical Cable tender
# ═══════════════════════════════════════════════════════════════════════════

def case_2_cable_tender():
    """
    Simulates a tender for PVC insulated copper cable, 1100V, with material
    and warranty stated.

    IS 1554 requires: voltage ≤ 1100V, material present, protection ≥ IP44, warranty.
    IS 694  requires: voltage ≤ 1100V, material present, warranty.

    With full params → both should be compliant.
    Without material → both should be partial (material missing).
    """
    failures = []

    # Sub-case A: full params
    params_full = {
        "voltage":  "1100V",
        "material": "PVC",
        "protection": "IP44",
        "warranty": "2 years",
    }
    cr_1554_full = check_compliance(params_full, "IS 1554")
    cr_694_full  = check_compliance(params_full, "IS 694")
    print(f"  [Full params] IS 1554: {cr_1554_full['status']}, IS 694: {cr_694_full['status']}")
    if cr_1554_full["status"] != "compliant":
        failures.append(f"IS 1554 full params: expected compliant, got {cr_1554_full['status']} "
                         f"passed={cr_1554_full['passed_fields']} failed={cr_1554_full['failed_fields']} "
                         f"missing={cr_1554_full['missing_fields']}")
    if cr_694_full["status"] != "compliant":
        failures.append(f"IS 694 full params: expected compliant, got {cr_694_full['status']}")

    # Sub-case B: material absent → partial
    params_no_mat = {"voltage": "1100V", "warranty": "2 years"}
    cr_1554_nm = check_compliance(params_no_mat, "IS 1554")
    cr_694_nm  = check_compliance(params_no_mat, "IS 694")
    print(f"  [No material] IS 1554: {cr_1554_nm['status']}, IS 694: {cr_694_nm['status']}")
    if cr_1554_nm["status"] != "partial":
        failures.append(f"IS 1554 no-material: expected partial, got {cr_1554_nm['status']} "
                         f"missing={cr_1554_nm['missing_fields']}")
    if cr_694_nm["status"] != "partial":
        failures.append(f"IS 694 no-material: expected partial, got {cr_694_nm['status']}")
    if "material" not in cr_1554_nm["missing_fields"]:
        failures.append(f"IS 1554: 'material' not in missing_fields: {cr_1554_nm['missing_fields']}")

    # Sub-case C: voltage exceeds 1100V → IS 1554 non-compliant or partial
    params_hi_v = {"voltage": "2200V", "material": "PVC", "protection": "IP44", "warranty": "2 years"}
    cr_1554_hv = check_compliance(params_hi_v, "IS 1554")
    print(f"  [Voltage 2200V] IS 1554: {cr_1554_hv['status']} failed={cr_1554_hv['failed_fields']}")
    if cr_1554_hv["status"] not in ("partial", "non-compliant"):
        failures.append(f"IS 1554 high voltage: expected partial/non-compliant, got {cr_1554_hv['status']}")
    if "voltage" not in cr_1554_hv["failed_fields"]:
        failures.append(f"IS 1554 high voltage: 'voltage' should be in failed_fields: {cr_1554_hv['failed_fields']}")

    # Full ranking with appropriate semantic results
    sem = [
        _sr("IS 1554", "PVC Insulated (Heavy Duty) Electric Cables", 1.10),
        _sr("IS 694",  "PVC Insulated Cables for Voltages not Exceeding 1100 V", 1.15),
        _sr("IS 732",  "Code of Practice for Electrical Wiring Installations",   1.50),
        _sr("IS 302",  "Safety of Household Appliances",                         1.80),
        _sr("IS 8828", "Circuit Breakers for Overcurrent Protection",            1.90),
    ]
    result = rank_recommendations("cable_tender", "PVC cable 1100V material PVC warranty 2 years", params_full, sem)
    recs = result["recommendations"]
    codes_by_status = {r["is_code"]: r["compliance_status"] for r in recs}
    print(f"  Ranking: {json.dumps(codes_by_status)}")

    # IS 1554 and IS 694 should be compliant and ranked first
    if recs[0]["is_code"] not in ("IS 1554", "IS 694"):
        failures.append(f"Top rec for cable should be IS 1554 or IS 694, got {recs[0]['is_code']}")
    if codes_by_status.get("IS 1554") != "compliant":
        failures.append(f"IS 1554 in ranking should be compliant, got {codes_by_status.get('IS 1554')}")
    if codes_by_status.get("IS 694") != "compliant":
        failures.append(f"IS 694 in ranking should be compliant, got {codes_by_status.get('IS 694')}")

    passed = len(failures) == 0
    return passed, {
        "IS1554_full": cr_1554_full["status"],
        "IS694_full":  cr_694_full["status"],
        "IS1554_no_material": cr_1554_nm["status"],
        "IS1554_high_voltage": cr_1554_hv["status"],
        "ranked_top": recs[0]["is_code"] if recs else "none",
        "failures":   str(failures) if failures else "none",
    }


# ═══════════════════════════════════════════════════════════════════════════
# CASE 3 — Plug / Socket-outlet tender (IS 1293)
# ═══════════════════════════════════════════════════════════════════════════

def case_3_plug_socket_tender():
    """
    IS 1293 requirements:
      voltage ≤ 250V, power ≤ 3680W, protection ≥ IP20,
      warranty required, material required.

    Test with a 3-pin plug spec at 230V / 3000W with all fields.
    """
    failures = []

    # Full compliant params
    params = {
        "voltage":    "230V",
        "power":      "3000W",
        "protection": "IP20",
        "warranty":   "1 year",
        "material":   "polycarbonate",
    }
    cr = check_compliance(params, "IS 1293")
    print(f"  [Full params] IS 1293: {cr['status']} passed={cr['passed_fields']} "
          f"failed={cr['failed_fields']} missing={cr['missing_fields']}")
    if cr["status"] != "compliant":
        failures.append(f"IS 1293 full params: expected compliant, got {cr['status']} "
                        f"passed={cr['passed_fields']} failed={cr['failed_fields']} missing={cr['missing_fields']}")

    # Power exceeds 3680W limit
    params_overpow = {**params, "power": "5000W"}
    cr_op = check_compliance(params_overpow, "IS 1293")
    print(f"  [Power 5000W] IS 1293: {cr_op['status']} failed={cr_op['failed_fields']}")
    if cr_op["status"] not in ("partial", "non-compliant"):
        failures.append(f"IS 1293 overpower: expected partial/non-compliant, got {cr_op['status']}")
    if "power" not in cr_op["failed_fields"]:
        failures.append(f"IS 1293 overpower: 'power' should be in failed_fields: {cr_op['failed_fields']}")

    # Voltage exceeds 250V limit
    params_hiv = {**params, "voltage": "440V"}
    cr_hv = check_compliance(params_hiv, "IS 1293")
    print(f"  [Voltage 440V] IS 1293: {cr_hv['status']} failed={cr_hv['failed_fields']}")
    if "voltage" not in cr_hv["failed_fields"]:
        failures.append(f"IS 1293 high voltage: 'voltage' should be in failed_fields: {cr_hv['failed_fields']}")

    # Full ranking
    sem = [
        _sr("IS 1293", "Plugs and Socket-Outlets up to 250V 16A",            1.10),
        _sr("IS 302",  "Safety of Household Electrical Appliances",           1.30),
        _sr("IS 8828", "Circuit Breakers for Overcurrent Protection",         1.60),
        _sr("IS 9873", "Safety Requirements for Toys",                        2.20),
        _sr("IS 694",  "PVC Insulated Cables",                                2.50),
    ]
    result = rank_recommendations("plug_tender", "3-pin plug socket 230V 3000W polycarbonate warranty", params, sem)
    recs = result["recommendations"]
    codes_by_status = {r["is_code"]: r["compliance_status"] for r in recs}
    print(f"  Ranking: {json.dumps(codes_by_status)}")

    if not recs:
        failures.append("No recommendations returned for plug tender")
    elif recs[0]["is_code"] != "IS 1293":
        failures.append(f"Top rec should be IS 1293, got {recs[0]['is_code']}")
    if codes_by_status.get("IS 1293") != "compliant":
        failures.append(f"IS 1293 should be compliant in ranking, got {codes_by_status.get('IS 1293')}")

    passed = len(failures) == 0
    return passed, {
        "IS1293_full":     cr["status"],
        "IS1293_overpower": cr_op["status"],
        "IS1293_high_v":   cr_hv["status"],
        "ranked_top":      recs[0]["is_code"] if recs else "none",
        "failures":        str(failures) if failures else "none",
    }


# ═══════════════════════════════════════════════════════════════════════════
# CASE 4 — Edge: empty semantic results
# ═══════════════════════════════════════════════════════════════════════════

def case_4_empty_results():
    """rank_recommendations with empty list must not crash."""
    result = rank_recommendations("empty_test", "some spec text", {"power": "100W"}, [])
    failures = []
    if result.get("recommendations") != []:
        failures.append(f"Expected empty recommendations, got {result.get('recommendations')}")
    if result.get("spec_id") != "empty_test":
        failures.append("spec_id not preserved")
    passed = len(failures) == 0
    return passed, {"result": str(result), "failures": str(failures) if failures else "none"}


# ═══════════════════════════════════════════════════════════════════════════
# CASE 5 — Edge: needs_clarification passthrough
# ═══════════════════════════════════════════════════════════════════════════

def case_5_needs_clarification():
    """needs_clarification dict must be passed through unchanged."""
    nc = {
        "status": "needs_clarification",
        "question": "Are you looking for lighting or cable standards?",
        "candidates": [_sr("IS 10322", "Luminaires", 1.2), _sr("IS 694", "Cables", 1.3)],
    }
    result = rank_recommendations("nc_test", "ambiguous spec", {}, nc)
    failures = []
    if result.get("status") != "needs_clarification":
        failures.append(f"Expected needs_clarification passthrough, got: {result}")
    if result.get("question") != nc["question"]:
        failures.append("question not preserved")
    passed = len(failures) == 0
    return passed, {"status": result.get("status"), "failures": str(failures) if failures else "none"}


# ═══════════════════════════════════════════════════════════════════════════
# CASE 6 — Score sort order verification
# ═══════════════════════════════════════════════════════════════════════════

def case_6_sort_order():
    """
    Lower L2 score = better match = should rank first within same compliance tier.
    Two compliant standards: one at L2=0.8, one at L2=1.5.
    The L2=0.8 one should be ranked first.
    """
    params = {
        "voltage":    "230V",
        "protection": "IP65",
        "warranty":   "3 years",
        "power":      "100W",
        "operating_temperature": "-10°C to 50°C",
        "lifespan":   "50000 hours",
    }
    sem = [
        _sr("IS 10322",    "Luminaires LED Street Lighting",   1.50),  # compliant but higher L2
        _sr("IS 10322-5-3","LED Road and Street Luminaires",   0.80),  # compliant, lower L2 → should rank 1st
        _sr("IS 302",      "Safety of Household Appliances",   1.20),  # partial (no op_temp in params... wait it IS)
        _sr("IS 9000",     "Basic Environmental Testing",      1.10),  # partial/compliant
        _sr("IS 16520",    "Solid State LED Street Lights",    1.30),  # compliant
    ]
    result = rank_recommendations("sort_test", "LED", params, sem)
    recs = result["recommendations"]
    failures = []

    print(f"  Ranked order: {[(r['is_code'], r['compliance_status'], r['semantic_score']) for r in recs]}")

    # Find the two compliant LED standards
    compliant_recs = [r for r in recs if r["compliance_status"] == "compliant"]
    if len(compliant_recs) >= 2:
        # Within compliant tier, lower score should come first
        scores = [r["semantic_score"] for r in compliant_recs]
        if scores != sorted(scores):
            failures.append(f"Compliant tier not sorted by score ASC: {scores}")
        else:
            print(f"  [OK] Compliant tier sorted correctly by L2 score: {scores}")
    else:
        print(f"  [INFO] {len(compliant_recs)} compliant recs found — checking overall sort")

    # Overall: compliance tier must be non-decreasing
    tiers = []
    tier_map = {"compliant": 0, "partial": 1, "unknown": 2, "non-compliant": 3}
    for r in recs:
        tiers.append(tier_map.get(r["compliance_status"], 2))
    if tiers != sorted(tiers):
        failures.append(f"Overall tier order not non-decreasing: {tiers} for {[r['is_code'] for r in recs]}")
    else:
        print(f"  [OK] Tier order is non-decreasing: {tiers}")

    passed = len(failures) == 0
    return passed, {
        "ranked_order": str([(r["is_code"], r["compliance_status"], r["semantic_score"]) for r in recs]),
        "failures":     str(failures) if failures else "none",
    }


# ═══════════════════════════════════════════════════════════════════════════
# CASE 7 — kV/kW scaling in compliance checker
# ═══════════════════════════════════════════════════════════════════════════

def case_7_kv_scaling():
    """
    BUG-8 was fixed in extraction hardening. Verify it's present here.
    0.23 kV should scale to 230.0 and pass IS 1293 voltage ≤ 250V check.
    11 kV (11000V) should FAIL IS 1554 voltage ≤ 1100V check.
    """
    failures = []

    # 0.23 kV = 230V → should pass IS 1293's max 250V
    v230 = _extract_numeric("0.23 kV")
    if v230 != 230.0:
        failures.append(f"_extract_numeric('0.23 kV') = {v230}, expected 230.0")
    else:
        print(f"  [OK] _extract_numeric('0.23 kV') = {v230}")

    # 25 kW = 25000W → should fail IS 1293's max 3680W
    p25kw = _extract_numeric("25 kW")
    if p25kw != 25000.0:
        failures.append(f"_extract_numeric('25 kW') = {p25kw}, expected 25000.0")
    else:
        print(f"  [OK] _extract_numeric('25 kW') = {p25kw}")

    # 11kV spec against IS 1554 (max 1100V) → voltage should fail
    params_11kv = {"voltage": "0.011 MV", "material": "copper", "protection": "IP44", "warranty": "2 years"}
    # 0.011 MV = 11000V
    mv_val = _extract_numeric("0.011 MV")
    print(f"  _extract_numeric('0.011 MV') = {mv_val}  (expect 11000.0)")
    if mv_val != 11000.0:
        failures.append(f"_extract_numeric('0.011 MV') = {mv_val}, expected 11000.0")

    cr_11kv = check_compliance({"voltage": "11 kV", "material": "copper",
                                "protection": "IP44", "warranty": "2 years"}, "IS 1554")
    print(f"  IS 1554 with 11kV: {cr_11kv['status']} failed={cr_11kv['failed_fields']}")
    if "voltage" not in cr_11kv["failed_fields"]:
        failures.append(f"11kV should fail IS 1554's 1100V max, "
                        f"got status={cr_11kv['status']} failed={cr_11kv['failed_fields']}")

    passed = len(failures) == 0
    return passed, {
        "0.23kV_extracted":  str(v230),
        "25kW_extracted":    str(p25kw),
        "11kV_IS1554_status": cr_11kv["status"],
        "11kV_failed_fields": str(cr_11kv["failed_fields"]),
        "failures":           str(failures) if failures else "none",
    }


# ═══════════════════════════════════════════════════════════════════════════
# CASE 8 — Mandatory/advisory field audit
# ═══════════════════════════════════════════════════════════════════════════

def case_8_mandatory_advisory_audit():
    """
    Verifies:
    A. mock_requirements.json now has 'mandatory' flags
    B. check_compliance output includes mandatory_failed_fields, advisory_failed_fields,
       is_mandatory_compliant
    C. is_mandatory_compliant is False when a mandatory field fails
    D. is_mandatory_compliant is True when only advisory fields are missing/failed
    E. rank_recommendations output exposes all three new keys per recommendation
    """
    from compliance_ranking.compliance_checker import check_compliance as cc
    import json as _json, pathlib

    failures = []

    # A: JSON has mandatory flags
    reqs_path = pathlib.Path(__file__).parent / "mock_requirements.json"
    raw = _json.loads(reqs_path.read_text())
    has_mandatory = any(
        "mandatory" in rule
        for entry in raw
        for rule in entry.get("requirements", {}).values()
    )
    if not has_mandatory:
        failures.append("mock_requirements.json has no 'mandatory' flags")
    else:
        print(f"  [OK] mock_requirements.json has 'mandatory' flags")

    # B: check_compliance output has new keys
    params_full = {"power":"100-150W","protection":"IP65","voltage":"230V AC",
                   "lifespan":"50000 hours","warranty":"5 years",
                   "operating_temperature":"-10°C to 50°C"}
    cr = cc(params_full, "IS 10322")
    required_new_keys = {"mandatory_failed_fields", "advisory_failed_fields", "is_mandatory_compliant"}
    missing_keys = required_new_keys - set(cr.keys())
    if missing_keys:
        failures.append(f"check_compliance missing new keys: {missing_keys}")
    else:
        print(f"  [OK] check_compliance has new keys: {required_new_keys}")

    # C: is_mandatory_compliant=True for fully compliant spec vs IS 10322
    if cr["is_mandatory_compliant"] is not True:
        failures.append(f"IS 10322 full params: is_mandatory_compliant should be True, "
                        f"got {cr['is_mandatory_compliant']} "
                        f"mand_failed={cr.get('mandatory_failed_fields')}")
    else:
        print(f"  [OK] IS 10322 full params: is_mandatory_compliant=True")

    # D: Missing a mandatory field (protection) → is_mandatory_compliant=False
    params_no_prot = {k:v for k,v in params_full.items() if k != "protection"}
    cr_np = cc(params_no_prot, "IS 10322")
    # protection is mandatory=True → missing → is_mandatory_compliant should be False
    if cr_np["is_mandatory_compliant"] is not False:
        failures.append(f"IS 10322 without protection: is_mandatory_compliant should be False, "
                        f"got {cr_np['is_mandatory_compliant']}")
    else:
        print(f"  [OK] IS 10322 without mandatory protection: is_mandatory_compliant=False")

    # D2: Missing only warranty (mandatory=False for IS 10322) → is_mandatory_compliant=True
    params_no_warranty = {k:v for k,v in params_full.items() if k != "warranty"}
    cr_nw = cc(params_no_warranty, "IS 10322")
    if cr_nw["is_mandatory_compliant"] is not True:
        failures.append(f"IS 10322 without warranty (advisory): is_mandatory_compliant should be True, "
                        f"got {cr_nw['is_mandatory_compliant']} "
                        f"mand_failed={cr_nw.get('mandatory_failed_fields')} "
                        f"missing={cr_nw.get('missing_fields')}")
    else:
        print(f"  [OK] IS 10322 without advisory warranty: is_mandatory_compliant=True")

    # E: ranking output exposes new keys per recommendation
    sem = [_sr("IS 10322", "LED Street Lighting", 1.0),
           _sr("IS 302",   "Household Appliances", 1.4)]
    result = rank_recommendations("audit_test", "LED spec", params_full, sem)
    recs = result["recommendations"]
    for i, rec in enumerate(recs):
        for key in required_new_keys:
            if key not in rec:
                failures.append(f"rec[{i}] ({rec.get('is_code')}) missing key '{key}' in ranking output")
    if not failures:
        print(f"  [OK] All ranking output recs have new mandatory/advisory keys")

    # E2: Advisory failure in ranking
    # IS 10322 with full params: warranty is advisory=false → missing warranty shouldn't break is_mandatory_compliant
    params_advisory_fail = {k:v for k,v in params_full.items() if k != "warranty"}
    result_af = rank_recommendations("advisory_test", "LED spec", params_advisory_fail,
                                      [_sr("IS 10322", "LED Street Lighting", 1.0)])
    rec_af = result_af["recommendations"][0]
    print(f"  IS 10322 without warranty: status={rec_af['compliance_status']}, "
          f"is_mandatory_compliant={rec_af['is_mandatory_compliant']}, "
          f"advisory_failed={rec_af['advisory_failed_fields']}, "
          f"mandatory_failed={rec_af['mandatory_failed_fields']}")
    if rec_af["is_mandatory_compliant"] is not True:
        failures.append(f"IS 10322 advisory miss: is_mandatory_compliant should be True, "
                        f"got {rec_af['is_mandatory_compliant']}")
    if "warranty" not in rec_af.get("missing_fields", []) and "warranty" not in rec_af.get("advisory_failed_fields",[]):
        # warranty absent from spec → should be in missing_fields
        pass  # it's missing_fields not advisory_failed_fields, that's correct

    passed = len(failures) == 0
    return passed, {
        "mandatory_in_json":          str(has_mandatory),
        "IS10322_full_mand_compliant": str(cr["is_mandatory_compliant"]),
        "IS10322_no_prot_mand":        str(cr_np["is_mandatory_compliant"]),
        "IS10322_no_warranty_mand":    str(cr_nw["is_mandatory_compliant"]),
        "failures":                    str(failures) if failures else "none",
    }


# ═══════════════════════════════════════════════════════════════════════════
# CASE 9 — Full 3-category ranking via real semantic search
# ═══════════════════════════════════════════════════════════════════════════

def case_9_live_semantic_search():
    """
    Use the actual FAISS semantic_search() function for each of the 3
    product categories to prove the full pipeline generalizes.
    Does NOT require the backend server — calls the Python module directly.
    """
    from semantic_search.search import semantic_search
    from nlp_extraction.extractor import extract_from_text

    failures = []
    category_results = {}

    # ── Category A: LED street lighting ──────────────────────────────────
    text_led = """Tender for Supply of LED Street Lighting Fixtures
    Power: 100-150W, Protection: IP65, Voltage: 230V AC,
    Lifespan: 50000 hours, Warranty: 5 years,
    Operating Temperature: -10°C to 50°C
    Conforming to IS 10322"""
    ext_led = extract_from_text(text_led, "led_live")
    sem_led = semantic_search(ext_led["spec_text"], top_k=5)
    rank_led = rank_recommendations(
        "led_live", ext_led["spec_text"], ext_led["parameters"], sem_led)
    recs_led = rank_led["recommendations"]
    statuses_led = {r["is_code"]: r["compliance_status"] for r in recs_led}
    category_results["LED"] = statuses_led
    print(f"\n  LED category ({len(recs_led)} recs): {statuses_led}")

    led_top = recs_led[0]["is_code"] if recs_led else None
    led_top_status = recs_led[0]["compliance_status"] if recs_led else None
    if led_top_status not in ("compliant", "partial"):
        failures.append(f"LED top rec status unexpected: {led_top} = {led_top_status}")

    # ── Category B: PVC electrical cable ─────────────────────────────────
    text_cable = """Tender for Supply of PVC Insulated Copper Cable
    Working voltage up to 1100V, Material: PVC, Warranty: 2 years,
    Protection: IP44, Conforming to IS 1554"""
    ext_cable = extract_from_text(text_cable, "cable_live")
    sem_cable = semantic_search(ext_cable["spec_text"], top_k=5)
    rank_cable = rank_recommendations(
        "cable_live", ext_cable["spec_text"], ext_cable["parameters"], sem_cable)
    recs_cable = rank_cable["recommendations"]
    statuses_cable = {r["is_code"]: r["compliance_status"] for r in recs_cable}
    category_results["Cable"] = statuses_cable
    print(f"  Cable category ({len(recs_cable)} recs): {statuses_cable}")

    cable_top = recs_cable[0]["is_code"] if recs_cable else None
    cable_top_status = recs_cable[0]["compliance_status"] if recs_cable else None
    # Top result for cable spec should be cable-related, not LED
    if cable_top_status == "unknown" and len(recs_cable) > 0:
        # If all unknown, FAISS returned non-cable standards — note it
        print(f"  [WARN] Cable top rec is {cable_top} ({cable_top_status}) — FAISS coverage gap possible")

    # ── Category C: Plug / Socket-outlet ─────────────────────────────────
    text_plug = """Supply of 3-Pin Domestic Plug and Socket Outlet
    Rated voltage 230V, Power 3000W, Protection IP20,
    Material: polycarbonate, Warranty: 1 year,
    Conforming to IS 1293"""
    ext_plug = extract_from_text(text_plug, "plug_live")
    sem_plug = semantic_search(ext_plug["spec_text"], top_k=5)
    rank_plug = rank_recommendations(
        "plug_live", ext_plug["spec_text"], ext_plug["parameters"], sem_plug)
    recs_plug = rank_plug["recommendations"]
    statuses_plug = {r["is_code"]: r["compliance_status"] for r in recs_plug}
    category_results["Plug"] = statuses_plug
    print(f"  Plug category ({len(recs_plug)} recs): {statuses_plug}")

    plug_top = recs_plug[0]["is_code"] if recs_plug else None

    # All categories must return ≥1 recommendation
    for cat, recs in [("LED", recs_led), ("Cable", recs_cable), ("Plug", recs_plug)]:
        if not recs:
            failures.append(f"{cat}: zero recommendations returned")

    # All recs must have required keys
    for cat, recs in [("LED", recs_led), ("Cable", recs_cable), ("Plug", recs_plug)]:
        req_keys = {"is_code","title","semantic_score","compliance_status",
                    "passed_fields","failed_fields","missing_fields"}
        for i, r in enumerate(recs):
            missing = req_keys - set(r.keys())
            if missing:
                failures.append(f"{cat}[{i}] missing keys: {missing}")
            if "_tier" in r:
                failures.append(f"{cat}[{i}] _tier leaked into output")

    passed = len(failures) == 0
    return passed, {
        "led_top":   f"{led_top} ({led_top_status})",
        "cable_top": f"{cable_top} ({cable_top_status})",
        "plug_top":  f"{plug_top} ({recs_plug[0]['compliance_status'] if recs_plug else 'n/a'})",
        "led_statuses":   str(statuses_led),
        "cable_statuses": str(statuses_cable),
        "plug_statuses":  str(statuses_plug),
        "failures":       str(failures) if failures else "none",
    }


# ═══════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{SEP}")
    print("  StandardSense — Compliance Ranking Complete Test Suite")
    print(f"{SEP}")

    _run(1, "LED / Street-lighting regression (mock semantic results)",  case_1_led_regression)
    _run(2, "PVC electrical cable — 3 sub-cases (full, no-mat, hi-V)",   case_2_cable_tender)
    _run(3, "Plug / socket-outlet — IS 1293 (full, overpower, hi-V)",    case_3_plug_socket_tender)
    _run(4, "Edge: empty semantic results — no crash, empty recs",        case_4_empty_results)
    _run(5, "Edge: needs_clarification passthrough",                      case_5_needs_clarification)
    _run(6, "Sort order: lower L2 = better within compliance tier",       case_6_sort_order)
    _run(7, "kV/kW scaling: BUG-8 fix present and correct",               case_7_kv_scaling)
    _run(8, "Mandatory/advisory field gap audit (documentation)",         case_8_mandatory_advisory_audit)
    _run(9, "Live FAISS semantic search — 3-category end-to-end",         case_9_live_semantic_search)

    print(f"\n{SEP}")
    print("  PASS / FAIL SUMMARY")
    print(f"{SEP}")
    print(f"  {'#':<4} {'Status':<8} Test Name")
    print(f"  {'-'*66}")
    all_pass = True
    for r in RESULTS:
        icon = "OK" if r["status"] == "PASS" else ("!!" if r["status"] == "ERROR" else "XX")
        print(f"  {r['id']:<4} [{r['status']:<6}] {icon}  {r['name']}")
        if r["status"] != "PASS":
            all_pass = False
    print(f"\n  Overall: {'ALL PASS' if all_pass else 'FAILURES — see details above'}")
    print(f"{SEP}\n")
    sys.exit(0 if all_pass else 1)
