"""
test_rag.py
-----------
Test suite for the StandardSense RAG explanation engine (rag_engine.py).

Validates:
- Test Case 1: Partial compliance explanation generation
- Test Case 2: Fully compliant explanation generation
- Test Case 3: Non-compliant explanation generation
- Test Case 4: Unknown compliance status handling
- Test Case 5: Needs clarification workflow handling
- Test Case 6: Input validation error handling for missing/invalid fields
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on sys.path for direct execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag_feedback.rag.rag_engine import (
    generate_explanation,
    generate_rag_response,
    validate_input,
)


def test_case_1_partial_compliance() -> None:
    """Test Case 1: Partial compliance recommendation output."""
    data = {
        "status": "ok",
        "spec_id": "sample_tender_01",
        "spec_text": "LED street lighting fixture, Power 100-150W, Protection IP65, Lifespan 50000 hours, Voltage 230V AC, Warranty 5 years",
        "recommendations": [
            {
                "is_code": "IS 10322",
                "title": "LED lighting fixtures",
                "semantic_score": 0.3939,
                "compliance_status": "partial",
                "passed_fields": ["protection_rating", "voltage"],
                "failed_fields": [],
                "missing_fields": ["warranty"],
            }
        ],
    }

    res = generate_rag_response(data)

    assert res["status"] == "ok", f"Expected status 'ok', got '{res.get('status')}'"
    assert res["spec_id"] == "sample_tender_01", f"Expected spec_id 'sample_tender_01', got '{res.get('spec_id')}'"
    assert len(res["explanations"]) == 1, f"Expected 1 explanation, got {len(res['explanations'])}"

    item = res["explanations"][0]
    assert item["is_code"] == "IS 10322", f"Expected IS code 'IS 10322', got '{item.get('is_code')}'"
    assert item["semantic_score"] == 0.3939, f"Expected semantic score 0.3939, got {item.get('semantic_score')}"
    assert item["compliance_status"] == "partial", f"Expected compliance_status 'partial', got '{item.get('compliance_status')}'"

    explanation = item["explanation"]
    assert "IS 10322" in explanation, f"IS code missing from explanation: {explanation}"
    assert "0.3939" in explanation, f"Semantic score missing from explanation: {explanation}"
    assert "partial" in explanation.lower(), f"Partial status missing from explanation: {explanation}"
    assert "protection_rating" in explanation, f"Passed field missing from explanation: {explanation}"
    assert "voltage" in explanation, f"Passed field missing from explanation: {explanation}"
    assert "warranty" in explanation, f"Missing field not noted in explanation: {explanation}"

    print("[PASS] Test Case 1: Partial compliance verified")


def test_case_2_fully_compliant() -> None:
    """Test Case 2: Fully compliant recommendation output."""
    data = {
        "status": "ok",
        "spec_id": "tender_002",
        "spec_text": "High tensile deformed steel bars Grade Fe 500D",
        "recommendations": [
            {
                "is_code": "IS 1786",
                "title": "High Strength Deformed Steel Bars and Wires for Concrete Reinforcement",
                "semantic_score": 0.1520,
                "compliance_status": "compliant",
                "passed_fields": ["grade", "material", "diameter"],
                "failed_fields": [],
                "missing_fields": [],
            }
        ],
    }

    res = generate_rag_response(data)

    assert res["status"] == "ok", f"Expected status 'ok', got '{res.get('status')}'"
    assert res["spec_id"] == "tender_002"
    assert len(res["explanations"]) == 1

    item = res["explanations"][0]
    assert item["is_code"] == "IS 1786"
    assert item["compliance_status"] == "compliant"
    assert "compliant" in item["explanation"].lower()
    assert "grade" in item["explanation"]
    assert "material" in item["explanation"]
    assert "diameter" in item["explanation"]

    print("[PASS] Test Case 2: Fully compliant verified")


def test_case_3_non_compliant() -> None:
    """Test Case 3: Non-compliant recommendation output."""
    data = {
        "status": "ok",
        "spec_id": "tender_003",
        "spec_text": "Distribution transformer 11kV / 433V copper winding",
        "recommendations": [
            {
                "is_code": "IS 1180",
                "title": "Outdoor Type Oil Immersed Distribution Transformers",
                "semantic_score": 0.4850,
                "compliance_status": "non-compliant",
                "passed_fields": ["voltage_rating"],
                "failed_fields": ["winding_material", "efficiency_level"],
                "missing_fields": [],
            }
        ],
    }

    res = generate_rag_response(data)

    assert res["status"] == "ok"
    assert res["spec_id"] == "tender_003"
    assert len(res["explanations"]) == 1

    item = res["explanations"][0]
    assert item["is_code"] == "IS 1180"
    assert item["compliance_status"] == "non-compliant"
    assert "non-compliant" in item["explanation"].lower()
    assert "winding_material" in item["explanation"]
    assert "efficiency_level" in item["explanation"]

    print("[PASS] Test Case 3: Non-compliant verified")


def test_case_4_unknown_compliance() -> None:
    """Test Case 4: Unknown compliance status handling."""
    data = {
        "status": "ok",
        "spec_id": "tender_004",
        "spec_text": "Custom specialized industrial filter assembly",
        "recommendations": [
            {
                "is_code": "IS 9000",
                "title": "Basic Environmental Testing Procedures for Electronic and Electrical Items",
                "semantic_score": 0.6210,
                "compliance_status": "unknown",
                "passed_fields": [],
                "failed_fields": [],
                "missing_fields": ["operating_temperature", "humidity_rating"],
            }
        ],
    }

    res = generate_rag_response(data)

    assert res["status"] == "ok"
    assert res["spec_id"] == "tender_004"
    assert len(res["explanations"]) == 1

    item = res["explanations"][0]
    assert item["is_code"] == "IS 9000"
    assert item["compliance_status"] == "unknown"
    assert "could not be determined" in item["explanation"].lower() or "unknown" in item["explanation"].lower()

    print("[PASS] Test Case 4: Unknown compliance verified")


def test_case_5_needs_clarification() -> None:
    """Test Case 5: Needs clarification request handling."""
    data = {
        "status": "needs_clarification",
        "question": "Are you seeking a standard for fire-retardant coated fabrics or uncoated woven fabrics?",
    }

    res = generate_rag_response(data)

    assert res["status"] == "needs_clarification", f"Expected status 'needs_clarification', got '{res.get('status')}'"
    assert res["question"] == data["question"], "Question was not preserved"
    assert "explanations" not in res, "Explanations should not be generated for needs_clarification"

    print("[PASS] Test Case 5: Needs clarification verified")


def test_case_6_invalid_input() -> None:
    """Test Case 6: Input validation error handling."""
    valid_base = {
        "spec_id": "tender_006",
        "spec_text": "Sample spec",
        "recommendations": [
            {
                "is_code": "IS 100",
                "title": "Standard Title",
                "semantic_score": 0.25,
                "compliance_status": "compliant",
                "passed_fields": ["field_a"],
                "failed_fields": [],
                "missing_fields": [],
            }
        ],
    }

    # 1. spec_id is missing
    bad_1 = dict(valid_base)
    del bad_1["spec_id"]
    try:
        validate_input(bad_1)
        assert False, "Should raise ValueError for missing spec_id"
    except ValueError as e:
        assert "spec_id" in str(e)
        print(f"[PASS] Caught missing spec_id: {e}")

    # 2. recommendations is missing
    bad_2 = dict(valid_base)
    del bad_2["recommendations"]
    try:
        validate_input(bad_2)
        assert False, "Should raise ValueError for missing recommendations"
    except ValueError as e:
        assert "recommendations" in str(e)
        print(f"[PASS] Caught missing recommendations: {e}")

    # 3. a recommendation is missing is_code
    bad_3 = {
        "spec_id": "tender_006",
        "spec_text": "Sample spec",
        "recommendations": [
            {
                "title": "Standard Title",
                "semantic_score": 0.25,
                "compliance_status": "compliant",
                "passed_fields": [],
                "failed_fields": [],
                "missing_fields": [],
            }
        ],
    }
    try:
        validate_input(bad_3)
        assert False, "Should raise ValueError for missing is_code in recommendation"
    except ValueError as e:
        assert "is_code" in str(e)
        print(f"[PASS] Caught missing is_code in recommendation: {e}")

    # 4. compliance_status is invalid
    bad_4 = {
        "spec_id": "tender_006",
        "spec_text": "Sample spec",
        "recommendations": [
            {
                "is_code": "IS 100",
                "title": "Standard Title",
                "semantic_score": 0.25,
                "compliance_status": "invalid_status",
                "passed_fields": [],
                "failed_fields": [],
                "missing_fields": [],
            }
        ],
    }
    try:
        validate_input(bad_4)
        assert False, "Should raise ValueError for invalid compliance_status"
    except ValueError as e:
        assert "compliance_status" in str(e)
        print(f"[PASS] Caught invalid compliance_status: {e}")

    print("[PASS] Test Case 6: Invalid input handling verified")


if __name__ == "__main__":
    print("=" * 72)
    print("RUNNING STANDARDSENSE RAG ENGINE TEST SUITE")
    print("=" * 72)
    test_case_1_partial_compliance()
    test_case_2_fully_compliant()
    test_case_3_non_compliant()
    test_case_4_unknown_compliance()
    test_case_5_needs_clarification()
    test_case_6_invalid_input()
    print("=" * 72)
    print("ALL RAG TESTS PASSED SUCCESSFULLY!")
    print("=" * 72)
