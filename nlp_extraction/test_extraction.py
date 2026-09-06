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

from nlp_extraction.extractor import extract_from_pdf, extract_from_text


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
        "Warranty 5 years, Operating temperature -10°C to 50°C, IS 10322"
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


if __name__ == "__main__":
    print("Running NLP Extraction test suite...\n")
    test_pdf_extraction()
    print()
    test_text_extraction()
    print("\nALL NLP EXTRACTION TESTS PASSED SUCCESSFULLY!")