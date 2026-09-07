"""
test_ranking_engine.py
----------------------
Integration test for compliance_ranking/ranking_engine.py.

Runs against REAL outputs from both upstream modules:
  - semantic_search.search.semantic_search()   (real FAISS index + model)
  - compliance_ranking.compliance_checker.check_compliance()  (real mock data)

Run from the project root with:
    $env:PYTHONIOENCODING = "utf-8"
    .\\venv\\Scripts\\python.exe compliance_ranking/test_ranking_engine.py
"""

from __future__ import annotations

import json
import pathlib
import sys

# Ensure the project root is on sys.path so both packages resolve correctly
# whether the script is run from the root or from inside compliance_ranking/.
ROOT = pathlib.Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Known-good real extraction output for sample_tender_01
# (LED street lighting fixture — validated earlier in this project)
# ---------------------------------------------------------------------------
SAMPLE_TENDER = {
    "spec_id":   "sample_tender_01",
    "spec_text": (
        "LED street lighting fixture, Power 100-150W, Protection IP65, "
        "Lifespan 50000 hours, Voltage 230V AC, Color temperature 4000K, "
        "Warranty 5 years, Operating temperature -10 deg C to 50 deg C, "
        "Application: Municipal road lighting, IS 10322"
    ),
    "parameters": {
        "power":               "100-150W",
        "protection":          "IP65",
        "lifespan":            "50000 hours",
        "voltage":             "230V AC",
        "color_temperature":   "4000K",
        "warranty":            "5 years",
        "operating_temperature": "-10 deg C to 50 deg C",
    },
}

# ---------------------------------------------------------------------------
# Ambiguous query — known to trigger needs_clarification from earlier testing
# ---------------------------------------------------------------------------
AMBIGUOUS_QUERY = "fire retardant fabric for industrial uniforms"


def separator(title: str, width: int = 72) -> str:
    return f"\n{'=' * width}\n{title}\n{'=' * width}"


def fmt_recommendation(i: int, rec: dict) -> str:
    lines = [
        f"  #{i}  {rec['is_code']}",
        f"      title:             {rec['title']}",
        f"      semantic_score:    {rec['semantic_score']}  (L2 dist — lower = closer)",
        f"      compliance_status: {rec['compliance_status']}",
        f"      passed_fields:     {rec['passed_fields']}",
        f"      failed_fields:     {rec['failed_fields']}",
        f"      missing_fields:    {rec['missing_fields']}",
    ]
    return "\n".join(lines)


def run_tests() -> str:
    """Execute all integration tests and return the full output as a string."""
    lines: list[str] = []
    log = lines.append

    # -----------------------------------------------------------------------
    # Import semantic search — triggers FAISS index + model load at import time
    # -----------------------------------------------------------------------
    log(separator("LOADING MODELS (FAISS + SentenceTransformer)"))
    log("Importing semantic_search.search — this loads the FAISS index and")
    log("downloads/caches the SentenceTransformer model. May take 15-60s...")

    from semantic_search.search import semantic_search, is_ambiguous  # noqa: PLC0415

    log("Models loaded successfully.")

    from compliance_ranking.ranking_engine import rank_recommendations  # noqa: PLC0415

    log("ranking_engine imported successfully.")

    # -----------------------------------------------------------------------
    # TEST 1: Confident path — LED street lighting spec
    # -----------------------------------------------------------------------
    log(separator("TEST 1: CONFIDENT PATH — LED Street Lighting Fixture"))
    log(f"spec_id:   {SAMPLE_TENDER['spec_id']}")
    log(f"spec_text: {SAMPLE_TENDER['spec_text']}")
    log(f"parameters: {json.dumps(SAMPLE_TENDER['parameters'], indent=12)}")

    log("\n--- Step 1a: Raw semantic_search() results ---")
    raw_results = semantic_search(SAMPLE_TENDER["spec_text"], top_k=5)
    for r in raw_results:
        log(
            f"  rank={r['rank']}  l2={r['l2_score']:.4f}  "
            f"{r['is_code']:10s}  {r['title'][:60]}"
        )

    ambiguous = is_ambiguous(raw_results)
    log(f"\n  is_ambiguous() -> {ambiguous}  (expected: False for a clear LED spec)")

    log("\n--- Step 1b: rank_recommendations() output ---")
    result = rank_recommendations(
        spec_id=SAMPLE_TENDER["spec_id"],
        spec_text=SAMPLE_TENDER["spec_text"],
        spec_parameters=SAMPLE_TENDER["parameters"],
        semantic_results=raw_results,
    )

    log(f"\n  spec_id:   {result['spec_id']}")
    log(f"  spec_text: {result['spec_text'][:80]}...")
    log(f"\n  recommendations ({len(result['recommendations'])} total, sorted by tier then semantic_score):\n")
    for i, rec in enumerate(result["recommendations"], start=1):
        log(fmt_recommendation(i, rec))
        log("")

    log("--- Step 1c: Ranking order verification ---")
    recs = result["recommendations"]

    # Map compliance_status -> tier integer using the same logic as ranking_engine
    _TIER = {"compliant": 0, "partial": 1, "unknown": 2, "non-compliant": 3}
    tier_order_ok = True
    for j in range(len(recs) - 1):
        curr = _TIER.get(recs[j]["compliance_status"], 2)
        nxt  = _TIER.get(recs[j + 1]["compliance_status"], 2)
        if curr > nxt:
            tier_order_ok = False
            log(
                f"  FAIL: tier order violated between "
                f"#{j+1} ({recs[j]['compliance_status']}) and "
                f"#{j+2} ({recs[j+1]['compliance_status']})"
            )
        elif curr == nxt:
            # Within same tier, semantic_score must be non-decreasing
            if recs[j]["semantic_score"] > recs[j + 1]["semantic_score"]:
                tier_order_ok = False
                log(
                    f"  FAIL: within-tier score order violated between "
                    f"#{j+1} (score={recs[j]['semantic_score']}) and "
                    f"#{j+2} (score={recs[j+1]['semantic_score']})"
                )

    if tier_order_ok:
        log("  PASS: all recommendations are in correct tier+score order.")

    # Compliance distribution summary
    from collections import Counter  # noqa: PLC0415
    dist = Counter(r["compliance_status"] for r in recs)
    log(f"\n  Compliance distribution: {dict(dist)}")
    log(
        "  Expected mix: electrical standards should show compliant/partial; "
        "structural/cement/food standards should show non-compliant or unknown "
        "(their fields — grade, material, dimensions — don't appear in the LED spec)."
    )

    # -----------------------------------------------------------------------
    # TEST 2: API-wrapped "ok" dict input (confirms dict unwrapping path)
    # -----------------------------------------------------------------------
    log(separator("TEST 2: API-WRAPPED INPUT (status='ok' dict passthrough)"))
    log("Wrapping the same raw results in the API response shape and re-ranking...")

    api_ok_response = {
        "status":  "ok",
        "results": [
            {
                "is_code":     r["is_code"],
                "title":       r["title"],
                "description": r["description"],
                "score":       r["l2_score"],   # API renames l2_score -> score
            }
            for r in raw_results
        ],
    }

    result_from_api = rank_recommendations(
        spec_id=SAMPLE_TENDER["spec_id"],
        spec_text=SAMPLE_TENDER["spec_text"],
        spec_parameters=SAMPLE_TENDER["parameters"],
        semantic_results=api_ok_response,
    )

    recs_direct = result["recommendations"]
    recs_api    = result_from_api["recommendations"]
    shapes_match = (
        len(recs_direct) == len(recs_api)
        and all(
            a["is_code"] == b["is_code"]
            and a["compliance_status"] == b["compliance_status"]
            for a, b in zip(recs_direct, recs_api)
        )
    )
    log(f"  Direct list input vs API-wrapped input produce identical ranking: {shapes_match}")
    if shapes_match:
        log("  PASS: both input shapes rank identically.")
    else:
        log("  FAIL: rankings differ between input shapes.")

    # -----------------------------------------------------------------------
    # TEST 3: Ambiguous path — needs_clarification passthrough
    # -----------------------------------------------------------------------
    log(separator("TEST 3: AMBIGUOUS PATH — needs_clarification passthrough"))
    log(f"Query: '{AMBIGUOUS_QUERY}'")

    ambig_raw = semantic_search(AMBIGUOUS_QUERY, top_k=5)
    log("\n  Raw semantic results:")
    for r in ambig_raw:
        log(
            f"    rank={r['rank']}  l2={r['l2_score']:.4f}  "
            f"{r['is_code']:10s}  {r['title'][:55]}"
        )

    ambig_flag = is_ambiguous(ambig_raw)
    log(f"\n  is_ambiguous() -> {ambig_flag}  (expected: True for fabric/uniform query)")

    # Build the needs_clarification dict the way the API would
    # (rank_recommendations accepts it whole if the caller passes the API response)
    ambig_api_response = {
        "status":     "needs_clarification",
        "question":   "(question would be generated by Groq — skipped in test)",
        "candidates": [
            {
                "is_code":     r["is_code"],
                "title":       r["title"],
                "description": r["description"],
                "score":       r["l2_score"],
            }
            for r in ambig_raw
        ],
    }

    passthrough = rank_recommendations(
        spec_id="ambiguous_test",
        spec_text=AMBIGUOUS_QUERY,
        spec_parameters={},
        semantic_results=ambig_api_response,
    )

    is_passthrough = (
        passthrough.get("status") == "needs_clarification"
        and "candidates" in passthrough
        and "question" in passthrough
        and passthrough is ambig_api_response   # same object, not a copy
    )
    log(f"\n  rank_recommendations returned status='needs_clarification': "
        f"{passthrough.get('status') == 'needs_clarification'}")
    log(f"  Response is the identical dict object (not re-wrapped): "
        f"{passthrough is ambig_api_response}")
    log(f"  'recommendations' key absent (not added by engine): "
        f"{'recommendations' not in passthrough}")
    log(f"  'candidates' key preserved: {'candidates' in passthrough}")
    if is_passthrough:
        log("  PASS: needs_clarification passed through unchanged.")
    else:
        log("  FAIL: passthrough not working correctly.")
        log(f"  Actual return value: {json.dumps(passthrough, indent=4)}")

    # Also test passing the raw ambiguous list directly (not the API dict)
    # to confirm rank_recommendations handles it without crashing —
    # raw list never carries needs_clarification status, so it gets ranked.
    log("\n  Bonus: passing ambiguous raw list directly (no API wrapper)...")
    log("  (raw list has no 'status' key, so engine will rank it regardless of ambiguity)")
    raw_passthrough = rank_recommendations(
        spec_id="ambiguous_raw_test",
        spec_text=AMBIGUOUS_QUERY,
        spec_parameters={},
        semantic_results=ambig_raw,
    )
    log(f"  Returned 'recommendations' list with {len(raw_passthrough['recommendations'])} entries: "
        f"{'PASS' if 'recommendations' in raw_passthrough else 'FAIL'}")

    # -----------------------------------------------------------------------
    # TEST 4: Error handling — check_compliance raises for a malformed IS code
    # -----------------------------------------------------------------------
    log(separator("TEST 4: ERROR HANDLING — compliance checker exception"))
    log("Passing a malformed IS code that will cause check_compliance to return 'unknown'")
    log("(IS codes not in mock_requirements.json return unknown — not an exception,")
    log(" but confirms the graceful fallback path is reachable)")

    error_candidates = [
        {"is_code": "IS 9999", "title": "Fictitious Standard", "l2_score": 0.42},
        {"is_code": "IS 1554", "title": "PVC Insulated Cables", "l2_score": 0.50},
    ]
    error_result = rank_recommendations(
        spec_id="error_test",
        spec_text="test",
        spec_parameters={"voltage": "230V AC"},
        semantic_results=error_candidates,
    )
    for rec in error_result["recommendations"]:
        log(f"  {rec['is_code']:10s}  status={rec['compliance_status']:15s}  score={rec['semantic_score']}")
    unknown_handled = any(
        r["is_code"] == "IS 9999" and r["compliance_status"] == "unknown"
        for r in error_result["recommendations"]
    )
    known_handled = any(
        r["is_code"] == "IS 1554" and r["compliance_status"] != "unknown"
        for r in error_result["recommendations"]
    )
    log(f"  Unknown IS code gracefully -> 'unknown': {unknown_handled}  "
        f"{'PASS' if unknown_handled else 'FAIL'}")
    log(f"  Known IS code still evaluated normally: {known_handled}  "
        f"{'PASS' if known_handled else 'FAIL'}")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    log(separator("SUMMARY"))
    log("  Test 1 (confident path + ranking order):  see PASS/FAIL above")
    log("  Test 2 (API-wrapped ok dict input):       " + ("PASS" if shapes_match else "FAIL"))
    log("  Test 3 (needs_clarification passthrough): " + ("PASS" if is_passthrough else "FAIL"))
    log("  Test 4 (error handling / unknown IS code):" + (
        " PASS" if (unknown_handled and known_handled) else " FAIL"
    ))

    return "\n".join(lines)


def verify_tier_order(recs: list[dict], log) -> bool:
    """
    Shared helper: walk the recommendations list and assert that
    (tier, semantic_score) is non-decreasing.  Logs any violation and
    returns True only if everything is correctly ordered.
    """
    _TIER = {"compliant": 0, "partial": 1, "unknown": 2, "non-compliant": 3}
    ok = True
    for j in range(len(recs) - 1):
        curr_tier  = _TIER.get(recs[j]["compliance_status"], 2)
        next_tier  = _TIER.get(recs[j + 1]["compliance_status"], 2)
        curr_score = recs[j]["semantic_score"]
        next_score = recs[j + 1]["semantic_score"]
        if curr_tier > next_tier:
            log(f"  FAIL: tier order violated at positions {j+1}->{j+2}: "
                f"{recs[j]['compliance_status']} > {recs[j+1]['compliance_status']}")
            ok = False
        elif curr_tier == next_tier and curr_score > next_score:
            log(f"  FAIL: within-tier score order violated at positions {j+1}->{j+2}: "
                f"score {curr_score} > {next_score} (same tier: {recs[j]['compliance_status']})")
            ok = False
    return ok


def run_edge_cases() -> str:
    """Execute the 5 edge case tests and return their output as a string."""
    lines: list[str] = []
    log = lines.append

    # Re-import — models are already cached after run_tests() loaded them,
    # so this is instantaneous.
    from semantic_search.search import semantic_search  # noqa: PLC0415
    from compliance_ranking.ranking_engine import rank_recommendations  # noqa: PLC0415

    results: dict[str, bool] = {}  # edge_case_name -> pass/fail

    # -------------------------------------------------------------------
    # EDGE CASE 1: Empty semantic_results list
    # -------------------------------------------------------------------
    log(separator("EDGE CASE 1: Empty semantic_results list"))
    log("Passing [] as semantic_results — zero candidates from search.")
    log("Expected: returns {'spec_id':..., 'spec_text':..., 'recommendations': []}")
    log("          no crash, no KeyError, no IndexError.")

    ec1_result = rank_recommendations(
        spec_id="ec1_empty",
        spec_text="some tender text",
        spec_parameters={"voltage": "230V AC"},
        semantic_results=[],
    )

    ec1_has_keys   = {"spec_id", "spec_text", "recommendations"} <= ec1_result.keys()
    ec1_empty_recs = ec1_result.get("recommendations") == []
    ec1_pass       = ec1_has_keys and ec1_empty_recs

    log(f"  Returned keys present (spec_id, spec_text, recommendations): {ec1_has_keys}")
    log(f"  recommendations is []: {ec1_empty_recs}")
    log(f"  spec_id preserved:     {ec1_result.get('spec_id') == 'ec1_empty'}")
    log(f"  Result: {'PASS' if ec1_pass else 'FAIL'}")
    log(f"  Full return value: {json.dumps(ec1_result, indent=4)}")
    results["EC1 empty list"] = ec1_pass

    # -------------------------------------------------------------------
    # EDGE CASE 2: IS code with NO entry in mock_requirements.json
    # -------------------------------------------------------------------
    log(separator("EDGE CASE 2: IS code absent from mock_requirements.json"))
    log("IS 732 (Code of Practice for Electrical Wiring Installations) is in the")
    log("FAISS index but has NO entry in mock_requirements.json.")
    log("Expected: compliance_status='unknown', all field lists empty, no crash.")
    log("Placed alongside a real partial result to confirm tier ordering too.")

    ec2_candidates = [
        # IS 732: not in requirements -> unknown (tier=2), score=0.80
        {"is_code": "IS 732",  "title": "Code of Practice for Electrical Wiring Installations", "l2_score": 0.80},
        # IS 1293: partial (tier=1), score=0.90 — worse semantic score but better tier
        {"is_code": "IS 1293", "title": "Plugs and Socket-Outlets",                             "l2_score": 0.90},
    ]
    ec2_result = rank_recommendations(
        spec_id="ec2_unknown_iscode",
        spec_text="LED street lighting fixture",
        spec_parameters=SAMPLE_TENDER["parameters"],
        semantic_results=ec2_candidates,
    )

    recs = ec2_result["recommendations"]
    ec2_is732   = next((r for r in recs if r["is_code"] == "IS 732"),  None)
    ec2_is1293  = next((r for r in recs if r["is_code"] == "IS 1293"), None)

    ec2_unknown_status = ec2_is732 is not None and ec2_is732["compliance_status"] == "unknown"
    ec2_empty_fields   = (
        ec2_is732 is not None
        and ec2_is732["passed_fields"]  == []
        and ec2_is732["failed_fields"]  == []
        and ec2_is732["missing_fields"] == []
    )
    # IS 1293 (partial, tier=1) must rank BEFORE IS 732 (unknown, tier=2)
    # even though IS 732 has the better (lower) semantic score
    ec2_order_ok = (
        recs[0]["is_code"] == "IS 1293"
        and recs[1]["is_code"] == "IS 732"
    )
    ec2_pass = ec2_unknown_status and ec2_empty_fields and ec2_order_ok

    log(f"\n  IS 732 compliance_status == 'unknown': {ec2_unknown_status}")
    log(f"  IS 732 all field lists are []:          {ec2_empty_fields}")
    log(f"  IS 1293 (partial, score=0.90) ranks before IS 732 (unknown, score=0.80): {ec2_order_ok}")
    log(f"  (IS 1293's worse semantic score is overridden by its better compliance tier)")
    for i, rec in enumerate(recs, start=1):
        log(f"    #{i}  {rec['is_code']:10s}  status={rec['compliance_status']:12s}  score={rec['semantic_score']}")
    log(f"  Result: {'PASS' if ec2_pass else 'FAIL'}")
    results["EC2 unknown IS code"] = ec2_pass

    # -------------------------------------------------------------------
    # EDGE CASE 3: All candidates tied on compliance_status — sort by score
    # -------------------------------------------------------------------
    log(separator("EDGE CASE 3: All candidates tied on compliance_status"))
    log("Three candidates all return 'partial' against the LED spec.")
    log("Scores assigned in REVERSE order to expose any insertion-order bug:")
    log("  IS 1293: l2_score=0.90  (worst semantic — should rank LAST within tier)")
    log("  IS 1554: l2_score=0.70  (middle)")
    log("  IS 694:  l2_score=0.55  (best semantic — should rank FIRST within tier)")
    log("Expected final order: IS 694 (0.55) -> IS 1554 (0.70) -> IS 1293 (0.90)")

    ec3_candidates = [
        # Deliberately given in worst-to-best score order to catch insertion-order bugs
        {"is_code": "IS 1293", "title": "Plugs and Socket-Outlets",        "l2_score": 0.90},
        {"is_code": "IS 1554", "title": "PVC Insulated Heavy Duty Cables", "l2_score": 0.70},
        {"is_code": "IS 694",  "title": "PVC Insulated Cables",            "l2_score": 0.55},
    ]
    ec3_result = rank_recommendations(
        spec_id="ec3_tied_tier",
        spec_text="LED street lighting fixture",
        spec_parameters=SAMPLE_TENDER["parameters"],
        semantic_results=ec3_candidates,
    )

    recs = ec3_result["recommendations"]
    ec3_all_partial    = all(r["compliance_status"] == "partial" for r in recs)
    ec3_scores_sorted  = [r["semantic_score"] for r in recs]
    ec3_order_correct  = ec3_scores_sorted == sorted(ec3_scores_sorted)
    ec3_first          = recs[0]["is_code"] == "IS 694"   if recs else False
    ec3_last           = recs[-1]["is_code"] == "IS 1293" if recs else False
    ec3_pass           = ec3_all_partial and ec3_order_correct and ec3_first and ec3_last

    log(f"\n  All 3 candidates returned 'partial': {ec3_all_partial}")
    log(f"  Scores in output (must be ascending): {ec3_scores_sorted}")
    log(f"  Scores are sorted ascending:          {ec3_order_correct}")
    log(f"  First entry is IS 694  (score=0.55):  {ec3_first}")
    log(f"  Last  entry is IS 1293 (score=0.90):  {ec3_last}")
    for i, rec in enumerate(recs, start=1):
        log(f"    #{i}  {rec['is_code']:10s}  status={rec['compliance_status']:12s}  score={rec['semantic_score']}")
    log(f"  Result: {'PASS' if ec3_pass else 'FAIL'}")
    results["EC3 tied-tier sort"] = ec3_pass

    # -------------------------------------------------------------------
    # EDGE CASE 4: spec_parameters is empty dict {} — all -> "unknown"
    # -------------------------------------------------------------------
    log(separator("EDGE CASE 4: spec_parameters = {} (empty dict)"))
    log("Real semantic results from the LED query, but no extracted parameters.")
    log("check_compliance() documented behavior: empty spec_parameters -> 'unknown'")
    log("Expected: all candidates come back 'unknown', sorted by semantic_score,")
    log("          no crash.")

    # Use real semantic results from the FAISS index
    raw_results = semantic_search(SAMPLE_TENDER["spec_text"], top_k=5)
    ec4_result = rank_recommendations(
        spec_id="ec4_empty_params",
        spec_text=SAMPLE_TENDER["spec_text"],
        spec_parameters={},    # <-- the edge case
        semantic_results=raw_results,
    )

    recs = ec4_result["recommendations"]
    ec4_all_unknown   = all(r["compliance_status"] == "unknown" for r in recs)
    ec4_scores_sorted = [r["semantic_score"] for r in recs]
    ec4_order_ok      = ec4_scores_sorted == sorted(ec4_scores_sorted)
    ec4_no_crash      = True   # reaching this line means no exception was raised
    ec4_pass          = ec4_all_unknown and ec4_order_ok and ec4_no_crash

    log(f"\n  All {len(recs)} candidates returned 'unknown': {ec4_all_unknown}")
    log(f"  Scores in output (must be ascending): {ec4_scores_sorted}")
    log(f"  Scores are sorted ascending:          {ec4_order_ok}")
    log(f"  No exception raised:                  {ec4_no_crash}")
    for i, rec in enumerate(recs, start=1):
        log(f"    #{i}  {rec['is_code']:10s}  status={rec['compliance_status']:12s}  "
            f"score={rec['semantic_score']}  missing={rec['missing_fields']}")
    log(f"  Result: {'PASS' if ec4_pass else 'FAIL'}")
    results["EC4 empty params"] = ec4_pass

    # -------------------------------------------------------------------
    # EDGE CASE 5: needs_clarification dict passed directly — passthrough
    # -------------------------------------------------------------------
    log(separator("EDGE CASE 5: needs_clarification dict passed as semantic_results"))
    log("Simulates a caller who gets the full API response and forwards it whole.")
    log("Expected: rank_recommendations() returns the IDENTICAL dict object,")
    log("          untouched — no 'recommendations' key added, no ranking attempted.")

    # Get real ambiguous raw results to build a realistic needs_clarification payload
    ambig_raw = semantic_search(AMBIGUOUS_QUERY, top_k=5)
    needs_clarification_payload = {
        "status":     "needs_clarification",
        "question":   "Are you looking for fire-resistant fabric standards or safety apparel standards?",
        "candidates": [
            {
                "is_code":     r["is_code"],
                "title":       r["title"],
                "description": r["description"],
                "score":       r["l2_score"],
            }
            for r in ambig_raw
        ],
    }

    ec5_result = rank_recommendations(
        spec_id="ec5_needs_clarification",
        spec_text=AMBIGUOUS_QUERY,
        spec_parameters={"material": "cotton"},
        semantic_results=needs_clarification_payload,
    )

    ec5_same_object         = ec5_result is needs_clarification_payload
    ec5_status_preserved    = ec5_result.get("status") == "needs_clarification"
    ec5_question_preserved  = ec5_result.get("question") == needs_clarification_payload["question"]
    ec5_candidates_count    = len(ec5_result.get("candidates", []))
    ec5_no_recommendations  = "recommendations" not in ec5_result
    ec5_no_spec_id          = "spec_id" not in ec5_result   # engine must NOT inject spec_id
    ec5_pass = (
        ec5_same_object
        and ec5_status_preserved
        and ec5_question_preserved
        and ec5_no_recommendations
        and ec5_no_spec_id
    )

    log(f"\n  Return value IS the same dict object (not a copy or re-wrap): {ec5_same_object}")
    log(f"  status == 'needs_clarification' preserved:                     {ec5_status_preserved}")
    log(f"  question text preserved verbatim:                               {ec5_question_preserved}")
    log(f"  candidates count preserved ({ec5_candidates_count} entries):            "
        f"{'PASS' if ec5_candidates_count == 5 else 'FAIL (expected 5)'}")
    log(f"  'recommendations' key NOT injected by engine:                  {ec5_no_recommendations}")
    log(f"  'spec_id' NOT injected by engine:                              {ec5_no_spec_id}")
    log(f"  Candidates list:")
    for c in ec5_result.get("candidates", []):
        log(f"    {c['is_code']:10s}  score={c['score']:.4f}  {c['title'][:50]}")
    log(f"  Result: {'PASS' if ec5_pass else 'FAIL'}")
    results["EC5 needs_clarification passthrough"] = ec5_pass

    # -------------------------------------------------------------------
    # Edge case summary
    # -------------------------------------------------------------------
    log(separator("EDGE CASE SUMMARY"))
    all_pass = all(results.values())
    for name, passed in results.items():
        log(f"  {'PASS' if passed else 'FAIL'}  {name}")
    log("")
    log(f"  Overall: {'ALL EDGE CASES PASS' if all_pass else 'ONE OR MORE EDGE CASES FAILED'}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Force UTF-8 stdout so degree symbols and em-dashes in IS titles
    # don't crash the Windows console.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

    # --- Integration tests (Prompt 4) ---
    integration_output = run_tests()
    print(integration_output)

    # --- Edge case tests (Prompt 5) ---
    print("\n" + "=" * 72)
    print("EDGE CASE TESTS (Prompt 5)")
    print("=" * 72)
    edge_output = run_edge_cases()
    print(edge_output)
