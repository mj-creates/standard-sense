"""
test_extraction.py
------------------
Test suite for StandardSense NLP Extraction (Team A).

Validates:
- Derivation of spec_id from the source PDF filename
- Construction of spec_text for Semantic Search compatibility
- Extraction of product name, specs, parameters, and explicit IS standards
"""

import json
import sys
from pathlib import Path

# Ensure project root is on sys.path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nlp_extraction.extractor import extract_from_pdf, extract_from_text, extract_parameters


def test_pdf_extraction() -> dict:
    """Test full extraction pipeline on sample_tender_01.pdf."""
    pdf_path = "data/sample_tenders/sample_tender_01.pdf"
    assert Path(pdf_path).exists(), f"Test PDF not found at {pdf_path}"

    result = extract_from_pdf(pdf_path)

    print("=" * 72)
    print("NLP EXTRACTION RESULT (Team A -> Semantic Search & Ranking)")
    print("=" * 72)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 72)

    # 1. Validate spec_id (derived from filename)
    expected_spec_id = "sample_tender_01"
    assert result["spec_id"] == expected_spec_id, (
        f"spec_id mismatch: expected '{expected_spec_id}', got '{result['spec_id']}'"
    )
    print(f"[OK] spec_id verified: {result['spec_id']}")

    # 2. Validate spec_text (natural language string for Semantic Search)
    expected_spec_text = (
        "LED street lighting fixture, Power 100-150W, Protection IP65, "
        "Lifespan 50000 hours, Voltage 230V AC, Color temperature 4000K, "
        "Warranty 5 years, Operating temperature -10°C to 50°C, "
        "Application: Municipal road lighting, IS 10322"
    )
    assert result["spec_text"] == expected_spec_text, (
        f"spec_text mismatch:\nExpected: {expected_spec_text}\nGot:      {result['spec_text']}"
    )
    print(f"[OK] spec_text verified: {result['spec_text']}")

    # 3. Validate structured fields preserved for Compliance & Ranking
    assert result["product"] == "LED street lighting fixture", (
        f"Product mismatch: {result['product']}"
    )
    print(f"[OK] product verified: {result['product']}")

    assert "IS 10322" in result["explicit_standards"], (
        f"Standard missing: {result['explicit_standards']}"
    )
    print(f"[OK] explicit_standards verified: {result['explicit_standards']}")

    params = result["parameters"]
    assert params.get("power") == "100-150W", f"Power mismatch: {params.get('power')}"
    assert params.get("protection") == "IP65", f"Protection mismatch: {params.get('protection')}"
    assert params.get("lifespan") == "50000 hours", f"Lifespan mismatch: {params.get('lifespan')}"
    assert params.get("voltage") == "230V AC", f"Voltage mismatch: {params.get('voltage')}"
    assert params.get("color_temperature") == "4000K", f"CCT mismatch: {params.get('color_temperature')}"
    assert params.get("warranty") == "5 years", f"Warranty mismatch: {params.get('warranty')}"
    assert "-10" in params.get("operating_temperature", ""), f"Temp mismatch: {params.get('operating_temperature')}"
    print(f"[OK] parameters verified ({len(params)} parameters detected)")

    assert len(result["specs"]) >= 8, f"Too few specs extracted: {len(result['specs'])}"
    print(f"[OK] specs verified ({len(result['specs'])} specifications extracted)")

    return result


def test_text_extraction() -> None:
    """Test extraction directly from raw text with custom spec_id."""
    sample_text = """
    Tender Title: Supply of High Tensile Deformed Steel Bars
    Technical Specifications:
    - Grade: Fe 500D
    - Material: mild steel
    - Dimensions: 12mm x 6m
    - Conforming to IS 1786:2008
    """
    res = extract_from_text(sample_text, spec_id="steel_tender_02")

    assert res["spec_id"] == "steel_tender_02"
    assert "Fe 500D" in res["spec_text"]
    assert "IS 1786:2008" in res["explicit_standards"]
    assert res["parameters"]["grade"] == "Fe 500D"
    assert res["parameters"]["material"] == "mild steel"
    assert res["parameters"]["dimensions"] == "12mm x 6m"
    print("[OK] Custom text extraction test passed")


def test_regression_team_b_tender_0091() -> None:
    """
    Regression tests for Team B sample tender TENDER_2026_0091:
    Issue 1: 'wattage range 100W-150W' -> power = '100-150W'
    Issue 2: 'housing material aluminium die-cast' -> material = 'aluminium die-cast'
    """
    print("=" * 72)
    print("REGRESSION TESTS (Team B -- TENDER_2026_0091)")
    print("=" * 72)

    sample_tender_text = """
    Tender Title: LED Street Light Fixtures TENDER_2026_0091
    Technical Requirements:
    - wattage range 100W-150W
    - housing material aluminium die-cast
    - protection IP66
    """
    res = extract_from_text(sample_tender_text, spec_id="TENDER_2026_0091")

    print(json.dumps(res, indent=2))

    # Issue 1: Power/wattage range extraction normalized to '100-150W'
    assert res["parameters"].get("power") == "100-150W", (
        f"Issue 1 failed: Expected power '100-150W', got '{res['parameters'].get('power')}'"
    )
    print(f"[OK] Issue 1 regression verified: power = '{res['parameters']['power']}'")

    # Issue 2: Complete multi-word / hyphenated material extraction
    assert res["parameters"].get("material") == "aluminium die-cast", (
        f"Issue 2 failed: Expected material 'aluminium die-cast', got '{res['parameters'].get('material')}'"
    )
    print(f"[OK] Issue 2 regression verified: material = '{res['parameters']['material']}'")

    # Protection parameter
    assert res["parameters"].get("protection") == "IP66", (
        f"Protection failed: got '{res['parameters'].get('protection')}'"
    )
    print(f"[OK] Protection verified: '{res['parameters']['protection']}'")

    # Isolated snippet tests
    snippet_1 = extract_parameters("wattage range 100W-150W")
    assert snippet_1.get("power") == "100-150W", (
        f"Snippet 1 failed: {snippet_1}"
    )
    print(f"[OK] Isolated snippet verified: 'wattage range 100W-150W' -> power = '{snippet_1['power']}'")

    snippet_2 = extract_parameters("housing material aluminium die-cast")
    assert snippet_2.get("material") == "aluminium die-cast", (
        f"Snippet 2 failed: {snippet_2}"
    )
    print(f"[OK] Isolated snippet verified: 'housing material aluminium die-cast' -> material = '{snippet_2['material']}'")

    # Verify semantic search spec_text reflects both correctly
    assert "Power 100-150W" in res["spec_text"], f"Power missing from spec_text: {res['spec_text']}"
    assert "Material aluminium die-cast" in res["spec_text"], f"Material missing from spec_text: {res['spec_text']}"
    print(f"[OK] spec_text contains updated parameters: {res['spec_text']}")


def test_regression_team_b_tender_0114() -> None:
    """
    Regression tests for Team B Sample 2: TENDER_2026_0114.
    Validates:
    - spec_text preserves: PVC insulated copper cable, working voltage up to 1100V,
      industrial power distribution, flame retardant sheath, conductor size 4 sq mm
    - Voltage requirement captured as structured parameter '1100V'
    - No false Material = PVC extracted from product name
    """
    print("=" * 72)
    print("REGRESSION TESTS (Team B -- TENDER_2026_0114)")
    print("=" * 72)

    tender_0114_text = """
    Tender Title: Supply of PVC insulated copper cable TENDER_2026_0114
    Product: PVC insulated copper cable
    Technical Specifications:
    - working voltage up to 1100V
    - industrial power distribution
    - flame retardant sheath
    - conductor size 4 sq mm
    """
    res = extract_from_text(tender_0114_text, spec_id="TENDER_2026_0114")

    print(json.dumps(res, indent=2))

    # 1. Verify spec_id and product
    assert res["spec_id"] == "TENDER_2026_0114", f"Unexpected spec_id: {res['spec_id']}"
    assert res["product"] == "PVC insulated copper cable", f"Unexpected product: {res['product']}"
    print(f"[OK] spec_id and product verified")

    # 2. Verify spec_text contains all required elements
    expected_elements = [
        "PVC insulated copper cable",
        "working voltage up to 1100V",
        "industrial power distribution",
        "flame retardant sheath",
        "conductor size 4 sq mm",
    ]
    for elem in expected_elements:
        assert elem in res["spec_text"], f"spec_text missing '{elem}': {res['spec_text']}"
        print(f"[OK] spec_text contains '{elem}'")

    # 3. Verify voltage requirement captured as 1100V in parameters
    assert res["parameters"].get("voltage") == "1100V", (
        f"Expected voltage '1100V', got '{res['parameters'].get('voltage')}'"
    )
    print(f"[OK] voltage verified: '{res['parameters']['voltage']}'")

    # 4. Verify no false Material parameter from product name
    assert "material" not in res["parameters"], (
        f"False material extracted: {res['parameters'].get('material')}"
    )
    print("[OK] No false material parameter from product name verified")

    # 5. Verify specifications list
    assert len(res["specs"]) == 4, f"Expected 4 specs, got {len(res['specs'])}"
    print(f"[OK] specs list verified ({len(res['specs'])} specifications)")


def test_nlp_issues_1_to_5() -> None:
    """
    Unit test coverage specifically addressing the 5 identified issues:
    - Issue 1: Power range normalizations and single value preservation
    - Issue 2: Meaningful multi-word / hyphenated material extraction
    - Issue 3: Voltage semantic requirement preservation in spec_text & parameter extraction
    - Issue 4: Information preservation from both parameters and specs in spec_text
    - Issue 5: No false material inference from product name; explicit material detection
    """
    print("=" * 72)
    print("UNIT TESTS FOR ISSUES 1 TO 5")
    print("=" * 72)

    # Issue 1: Power Range & Single Values
    assert extract_parameters("wattage range 100W-150W").get("power") == "100-150W"
    assert extract_parameters("100W-150W").get("power") == "100-150W"
    assert extract_parameters("100-150W").get("power") == "100-150W"
    assert extract_parameters("100 - 150 W").get("power") == "100-150W"
    assert extract_parameters("150W").get("power") == "150W"
    assert extract_parameters("25 kW").get("power") == "25 kW"
    assert "power" not in extract_parameters("industrial power distribution")
    print("[OK] Issue 1 (Power Range & Single Values) tests passed")

    # Issue 2: Material Preservation
    mat_test = extract_parameters("housing material aluminium die-cast")
    assert mat_test.get("material") == "aluminium die-cast", f"Got: {mat_test}"
    print("[OK] Issue 2 (Multi-word Material Preservation) tests passed")

    # Issue 3: Voltage Semantic Information & Voltage Parameter Extraction
    v_param = extract_parameters("working voltage up to 1100V")
    assert v_param.get("voltage") == "1100V", f"Got: {v_param}"
    v_ext = extract_from_text("- working voltage up to 1100V")
    assert "working voltage up to 1100V" in v_ext["spec_text"], f"Got: {v_ext['spec_text']}"
    # Standard voltage preservation
    v_std = extract_parameters("Operating voltage: 230V AC")
    assert v_std.get("voltage") == "230V AC", f"Got: {v_std}"
    print("[OK] Issue 3 (Voltage Semantic Information) tests passed")

    # Issue 4: Information preserved from both parameters & specs in spec_text
    tender_text = """
    Product: PVC insulated copper cable
    Technical Specifications:
    - working voltage up to 1100V
    - industrial power distribution
    - flame retardant sheath
    - conductor size 4 sq mm
    """
    res_4 = extract_from_text(tender_text, spec_id="TENDER_2026_0114")
    for req in ["PVC insulated copper cable", "working voltage up to 1100V", "industrial power distribution", "flame retardant sheath", "conductor size 4 sq mm"]:
        assert req in res_4["spec_text"], f"Missing '{req}' in {res_4['spec_text']}"
    print("[OK] Issue 4 (spec_text preservation without information loss) tests passed")

    # Issue 5: No false material from product name; explicit materials supported
    assert "material" not in extract_parameters("PVC insulated copper cable")
    assert extract_parameters("Material: PVC").get("material") == "PVC"
    assert extract_parameters("Housing material: PVC").get("material") == "PVC"
    assert extract_parameters("Construction material: PVC").get("material") == "PVC"
    assert extract_parameters("Body material: PVC").get("material") == "PVC"
    print("[OK] Issue 5 (False Material Prevention & Explicit Material Extraction) tests passed")


if __name__ == "__main__":
    print("Running NLP Extraction test suite...\n")
    test_pdf_extraction()
    print()
    test_text_extraction()
    print()
    test_regression_team_b_tender_0091()
    print()
    test_regression_team_b_tender_0114()
    print()
    test_nlp_issues_1_to_5()
    print("\nALL NLP EXTRACTION TESTS PASSED SUCCESSFULLY!")