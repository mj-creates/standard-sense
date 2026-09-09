"""
test_multilingual.py
--------------------
Test suite for StandardSense multilingual NLP normalization pipeline.

Coverage
--------
1.  detect_non_english_script()
    - Pure ASCII / English text  → (False, [])
    - Hindi (Devanagari) text    → (True, ["Devanagari"])
    - Tamil text                 → (True, ["Tamil"])
    - Telugu text                → (True, ["Telugu"])
    - Marathi (Devanagari) text  → (True, ["Devanagari"])
    - Bengali text               → (True, ["Bengali"])
    - Gujarati text              → (True, ["Gujarati"])
    - Mixed English + Hindi doc  → (True, ["Devanagari"])
    - Edge cases: empty, whitespace-only, digits-only

2.  normalize_text() — pass-through contract
    - English input is returned byte-for-byte unchanged
    - metadata["was_translated"] is False for English
    - metadata["original_language"] == "English" for English

3.  normalize_text() + translate_to_english() — live Groq integration
    - Hindi tender text is translated to English
    - Output contains standard English parameter keys (Power, Voltage, etc.)
    - Critical numeric values and units are preserved verbatim
    - IS codes are preserved verbatim
    - metadata["was_translated"] is True
    - metadata["translation_success"] is True

4.  Full pipeline regression — extract_from_text() with regional language input
    - Hindi tender → structured dict with standard English keys
    - Tamil tender snippet → parameters extracted correctly post-translation
    - Telugu tender snippet → parameters extracted correctly post-translation
    - multilingual_meta present in every extract_from_text() result
    - multilingual_meta["was_translated"] == False for English input (zero overhead)

5.  Graceful degradation
    - Missing GROQ_API_KEY → original text returned, translation_success=False
    - Empty text → no crash, returns ("", metadata with was_translated=False)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root on sys.path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nlp_extraction.multilingual import (
    detect_non_english_script,
    normalize_text,
    translate_to_english,
)
from nlp_extraction.extractor import extract_from_text

SEP  = "=" * 72
SEP2 = "-" * 72

def _section(title: str) -> None:
    print(f"\n{SEP}\n  {title}\n{SEP}")


# ---------------------------------------------------------------------------
# 1. detect_non_english_script
# ---------------------------------------------------------------------------

def test_detect_english_text() -> None:
    """Pure ASCII English text must not trigger detection."""
    _section("TEST 1a — detect_non_english_script: pure English")

    english_samples = [
        "Supply of LED street lighting fixture, Power: 100-150W, IP65",
        "Tender Title: PVC Insulated Copper Cable, Voltage up to 1100V",
        "Technical Specifications: Grade Fe 500D, IS 1786:2008",
        "",
        "   ",
        "12345 100W 230V AC IS 10322",
    ]
    for sample in english_samples:
        is_ne, scripts = detect_non_english_script(sample)
        assert not is_ne, f"False positive on English text: '{sample[:60]}'"
        assert scripts == [], f"Scripts detected for English text: {scripts}"
    print(f"[OK] {len(english_samples)} English samples correctly identified as non-regional")


def test_detect_devanagari() -> None:
    """Hindi and Marathi (Devanagari script) must be detected."""
    _section("TEST 1b — detect_non_english_script: Devanagari (Hindi/Marathi)")

    # Hindi: "LED सड़क प्रकाश स्थिरता की आपूर्ति, शक्ति: 100-150W"
    hindi_text = (
        "LED सड़क प्रकाश स्थिरता की आपूर्ति\n"
        "शक्ति: 100-150W\n"
        "वोल्टेज: 230V AC\n"
        "सुरक्षा रेटिंग: IP65\n"
        "जीवनकाल: 50000 घंटे\n"
        "वारंटी: 5 वर्ष\n"
        "मानक: IS 10322"
    )
    is_ne, scripts = detect_non_english_script(hindi_text)
    assert is_ne, "Devanagari (Hindi) text not detected"
    assert "Devanagari" in scripts, f"Expected 'Devanagari' in {scripts}"
    print(f"[OK] Hindi (Devanagari) detected: scripts={scripts}")

    # Marathi: "एलईडी पथदिव्यांचा पुरवठा, शक्ती: 150W, संरक्षण: IP65"
    marathi_text = "एलईडी पथदिव्यांचा पुरवठा, शक्ती: 150W, संरक्षण: IP65, IS 10322"
    is_ne, scripts = detect_non_english_script(marathi_text)
    assert is_ne, "Devanagari (Marathi) text not detected"
    assert "Devanagari" in scripts
    print(f"[OK] Marathi (Devanagari) detected: scripts={scripts}")


def test_detect_tamil() -> None:
    """Tamil script must be detected."""
    _section("TEST 1c — detect_non_english_script: Tamil")

    # Tamil: "எல்இடி தெரு விளக்கு, சக்தி: 100-150W, மின்னழுத்தம்: 230V AC"
    tamil_text = (
        "எல்இடி தெரு விளக்கு வழங்கல்\n"
        "சக்தி: 100-150W\n"
        "மின்னழுத்தம்: 230V AC\n"
        "பாதுகாப்பு மதிப்பீடு: IP65\n"
        "IS 10322"
    )
    is_ne, scripts = detect_non_english_script(tamil_text)
    assert is_ne, "Tamil text not detected"
    assert "Tamil" in scripts, f"Expected 'Tamil' in {scripts}"
    print(f"[OK] Tamil detected: scripts={scripts}")


def test_detect_telugu() -> None:
    """Telugu script must be detected."""
    _section("TEST 1d — detect_non_english_script: Telugu")

    # Telugu: "LED వీధి దీపాల సరఫరా, విద్యుత్ శక్తి: 100-150W, వోల్టేజ్: 230V AC"
    telugu_text = (
        "LED వీధి దీపాల సరఫరా\n"
        "విద్యుత్ శక్తి: 100-150W\n"
        "వోల్టేజ్: 230V AC\n"
        "రక్షణ రేటింగ్: IP65\n"
        "IS 10322"
    )
    is_ne, scripts = detect_non_english_script(telugu_text)
    assert is_ne, "Telugu text not detected"
    assert "Telugu" in scripts, f"Expected 'Telugu' in {scripts}"
    print(f"[OK] Telugu detected: scripts={scripts}")


def test_detect_bengali() -> None:
    """Bengali script must be detected."""
    _section("TEST 1e — detect_non_english_script: Bengali")

    # Bengali: "এলইডি রাস্তার আলো সরবরাহ, শক্তি: 100-150W"
    bengali_text = "এলইডি রাস্তার আলো সরবরাহ, শক্তি: 100-150W, ভোল্টেজ: 230V AC, IS 10322"
    is_ne, scripts = detect_non_english_script(bengali_text)
    assert is_ne, "Bengali text not detected"
    assert "Bengali" in scripts, f"Expected 'Bengali' in {scripts}"
    print(f"[OK] Bengali detected: scripts={scripts}")


def test_detect_gujarati() -> None:
    """Gujarati script must be detected."""
    _section("TEST 1f — detect_non_english_script: Gujarati")

    # Gujarati: "LED શેરી લાઇટ પ્રકાશ, શક્તિ: 150W, વોલ્ટેજ: 230V AC"
    gujarati_text = "LED શેરી લાઇટ પ્રકાશ, શક્તિ: 150W, વોલ્ટેજ: 230V AC, IS 10322"
    is_ne, scripts = detect_non_english_script(gujarati_text)
    assert is_ne, "Gujarati text not detected"
    assert "Gujarati" in scripts, f"Expected 'Gujarati' in {scripts}"
    print(f"[OK] Gujarati detected: scripts={scripts}")


def test_detect_mixed_english_hindi() -> None:
    """Mixed document (English headers + Hindi body) must trigger detection."""
    _section("TEST 1g — detect_non_english_script: mixed English + Hindi")

    # Realistic scenario: English section header, Hindi content
    mixed_text = (
        "TECHNICAL SPECIFICATIONS\n"
        "Product: LED Street Light\n"
        "शक्ति: 100-150W\n"           # Hindi: Power
        "वोल्टेज: 230V AC\n"           # Hindi: Voltage
        "Protection Rating: IP65\n"
        "Warranty: 5 years"
    )
    is_ne, scripts = detect_non_english_script(mixed_text)
    assert is_ne, "Mixed English+Hindi text not detected as non-English"
    assert "Devanagari" in scripts
    print(f"[OK] Mixed English+Hindi detected: scripts={scripts}")


def test_detect_edge_cases() -> None:
    """Edge cases: empty string, whitespace only, digits only, None-like."""
    _section("TEST 1h — detect_non_english_script: edge cases")

    is_ne, scripts = detect_non_english_script("")
    assert not is_ne and scripts == [], f"Empty string failed: {is_ne}, {scripts}"
    print("[OK] Empty string → (False, [])")

    is_ne, scripts = detect_non_english_script("   \n\t  ")
    assert not is_ne and scripts == [], f"Whitespace-only failed: {is_ne}, {scripts}"
    print("[OK] Whitespace-only → (False, [])")

    is_ne, scripts = detect_non_english_script("100 230 50000 IP65 IS10322")
    assert not is_ne and scripts == [], f"Digits+ASCII failed: {is_ne}, {scripts}"
    print("[OK] Digits/ASCII only → (False, [])")


# ---------------------------------------------------------------------------
# 2. normalize_text — English pass-through contract
# ---------------------------------------------------------------------------

def test_normalize_passthrough_english() -> None:
    """English text must pass through normalize_text completely unchanged."""
    _section("TEST 2 — normalize_text: English pass-through (zero-cost)")

    english_samples = [
        "Supply of LED street lighting fixture, Power: 100-150W, IP65, IS 10322",
        "Tender Title: PVC Insulated Copper Cable\n- working voltage up to 1100V",
        "Grade: Fe 500D, Material: mild steel, IS 1786:2008",
    ]
    for original in english_samples:
        result_text, meta = normalize_text(original)

        assert result_text == original, (
            f"English text was modified!\nOriginal: {original}\nGot:      {result_text}"
        )
        assert meta["was_translated"] is False, f"was_translated should be False: {meta}"
        assert meta["detected_scripts"] == [], f"Scripts should be empty: {meta}"
        assert meta["original_language"] == "English", f"Language should be 'English': {meta}"
        assert meta["translation_success"] is False
        print(f"[OK] Pass-through verified for: '{original[:60]}...'")


# ---------------------------------------------------------------------------
# 3. Live Groq translation — Hindi tender
# ---------------------------------------------------------------------------

def test_translate_hindi_tender() -> None:
    """
    Full Groq API call: Hindi LED street light tender →
    English output with standard parameter keys and preserved numerics.
    Requires GROQ_API_KEY to be set.
    """
    _section("TEST 3 — translate_to_english: Hindi tender (live Groq API)")

    if not os.environ.get("GROQ_API_KEY"):
        print("[SKIP] GROQ_API_KEY not set — skipping live API test")
        return

    hindi_tender = (
        "उत्पाद: एलईडी स्ट्रीट लाइटिंग फिक्सचर\n"
        "तकनीकी विशिष्टताएं:\n"
        "- शक्ति: 100-150W\n"
        "- वोल्टेज: 230V AC\n"
        "- सुरक्षा रेटिंग: IP65\n"
        "- जीवनकाल: 50000 घंटे\n"
        "- वारंटी: 5 वर्ष\n"
        "- मानक: IS 10322"
    )

    _, detected_scripts = detect_non_english_script(hindi_tender)
    translated, success = translate_to_english(hindi_tender, detected_scripts)

    print(f"  Detected scripts  : {detected_scripts}")
    print(f"  Translation success: {success}")
    print(f"  Translated text:\n{translated}")
    print()

    assert success, "Groq API translation failed — check API key and model availability"

    # Numeric values and units must be preserved verbatim
    for value in ["100-150W", "230V", "IP65", "50000", "IS 10322"]:
        assert value in translated, (
            f"Critical value '{value}' missing from translation:\n{translated}"
        )
        print(f"  [OK] Value preserved: '{value}'")

    # Output should be in English (contain common English parameter words)
    translated_lower = translated.lower()
    english_terms_found = sum(
        1 for term in ["power", "voltage", "protection", "lifespan", "warranty"]
        if term in translated_lower
    )
    assert english_terms_found >= 3, (
        f"Expected ≥3 English parameter terms, found {english_terms_found}:\n{translated}"
    )
    print(f"  [OK] {english_terms_found}/5 English parameter terms present in translation")


# ---------------------------------------------------------------------------
# 4. Full pipeline regression — extract_from_text with regional input
# ---------------------------------------------------------------------------

def test_pipeline_hindi_full() -> None:
    """
    End-to-end: Hindi LED tender → extract_from_text → structured dict
    with standard English keys and correct numeric values.
    Requires GROQ_API_KEY.
    """
    _section("TEST 4a — Full pipeline: Hindi tender → extract_from_text")

    if not os.environ.get("GROQ_API_KEY"):
        print("[SKIP] GROQ_API_KEY not set — skipping live pipeline test")
        return

    hindi_tender = (
        "उत्पाद: एलईडी स्ट्रीट लाइटिंग फिक्सचर\n"
        "तकनीकी विशिष्टताएं:\n"
        "- शक्ति: 100-150W\n"
        "- वोल्टेज: 230V AC\n"
        "- सुरक्षा रेटिंग: IP65\n"
        "- जीवनकाल: 50000 घंटे\n"
        "- वारंटी: 5 वर्ष\n"
        "- तापमान: -10°C से 50°C\n"
        "- मानक: IS 10322"
    )

    result = extract_from_text(hindi_tender, spec_id="hindi_tender_test")

    import json
    print(f"  Output:\n{json.dumps(result, indent=2, ensure_ascii=False)}")

    # multilingual_meta must always be present
    assert "multilingual_meta" in result, "multilingual_meta key missing from result"
    meta = result["multilingual_meta"]
    assert meta["was_translated"] is True, f"was_translated should be True: {meta}"
    assert meta["translation_success"] is True, f"Translation should have succeeded: {meta}"
    assert "Devanagari" in meta["detected_scripts"], f"Devanagari not in scripts: {meta}"
    print(f"  [OK] multilingual_meta: {meta}")

    # Core numeric values must survive translation → extraction
    for value in ["100-150W", "230V", "IP65", "50000"]:
        assert value in result["spec_text"], (
            f"Value '{value}' not found in spec_text after Hindi→English pipeline:\n"
            f"{result['spec_text']}"
        )
        print(f"  [OK] Value in spec_text: '{value}'")

    # IS code must be extracted
    assert "IS 10322" in result["explicit_standards"], (
        f"IS 10322 not extracted: {result['explicit_standards']}"
    )
    print(f"  [OK] IS 10322 in explicit_standards")

    # Parameters dict must have at least power, voltage, protection
    params = result["parameters"]
    assert params.get("power"), f"power parameter missing: {params}"
    assert params.get("voltage"), f"voltage parameter missing: {params}"
    assert params.get("protection"), f"protection parameter missing: {params}"
    print(f"  [OK] Parameters extracted: {params}")


def test_pipeline_tamil_snippet() -> None:
    """
    Tamil snippet → translate → extract_from_text → parameters present.
    """
    _section("TEST 4b — Full pipeline: Tamil snippet → extract_from_text")

    if not os.environ.get("GROQ_API_KEY"):
        print("[SKIP] GROQ_API_KEY not set — skipping live pipeline test")
        return

    # Tamil: "LED தெரு விளக்கு, சக்தி: 150W, மின்னழுத்தம்: 230V AC, IP65"
    tamil_text = (
        "LED தெரு விளக்கு வழங்கல்\n"
        "சக்தி: 150W\n"
        "மின்னழுத்தம்: 230V AC\n"
        "பாதுகாப்பு: IP65\n"
        "உத்தரவாதம்: 3 years\n"
        "IS 10322"
    )

    result = extract_from_text(tamil_text, spec_id="tamil_snippet_test")

    meta = result["multilingual_meta"]
    assert meta["was_translated"] is True, f"Tamil not translated: {meta}"
    assert "Tamil" in meta["detected_scripts"]
    print(f"  [OK] Tamil detected and translated: {meta}")

    params = result["parameters"]
    assert params.get("voltage"), f"Voltage not extracted from Tamil snippet: {params}"
    assert params.get("protection"), f"Protection not extracted from Tamil snippet: {params}"
    print(f"  [OK] Parameters extracted from Tamil: {params}")


def test_pipeline_telugu_snippet() -> None:
    """
    Telugu snippet → translate → extract_from_text → parameters present.
    """
    _section("TEST 4c — Full pipeline: Telugu snippet → extract_from_text")

    if not os.environ.get("GROQ_API_KEY"):
        print("[SKIP] GROQ_API_KEY not set — skipping live pipeline test")
        return

    # Telugu: "LED వీధి దీపాల సరఫరా, విద్యుత్ శక్తి: 150W, వోల్టేజ్: 230V AC"
    telugu_text = (
        "LED వీధి దీపాల సరఫరా\n"
        "విద్యుత్ శక్తి: 150W\n"
        "వోల్టేజ్: 230V AC\n"
        "రక్షణ రేటింగ్: IP65\n"
        "హామీ: 3 years\n"
        "IS 10322"
    )

    result = extract_from_text(telugu_text, spec_id="telugu_snippet_test")

    meta = result["multilingual_meta"]
    assert meta["was_translated"] is True, f"Telugu not translated: {meta}"
    assert "Telugu" in meta["detected_scripts"]
    print(f"  [OK] Telugu detected and translated: {meta}")

    params = result["parameters"]
    assert params.get("voltage"), f"Voltage not extracted from Telugu snippet: {params}"
    assert params.get("protection"), f"Protection not extracted from Telugu snippet: {params}"
    print(f"  [OK] Parameters extracted from Telugu: {params}")


def test_multilingual_meta_always_present() -> None:
    """
    multilingual_meta must be present in ALL extract_from_text() results,
    including pure English input — key must never be absent.
    """
    _section("TEST 4d — multilingual_meta always present in output")

    english_text = "Supply of PVC insulated copper cable, Voltage: 230V AC"
    result = extract_from_text(english_text, spec_id="meta_presence_test")

    assert "multilingual_meta" in result, (
        "multilingual_meta key missing from English extract_from_text() output"
    )
    meta = result["multilingual_meta"]
    # All four keys must always be present
    for key in ("was_translated", "detected_scripts", "translation_success", "original_language"):
        assert key in meta, f"multilingual_meta missing key '{key}': {meta}"
    assert meta["was_translated"] is False
    assert meta["original_language"] == "English"
    print(f"[OK] multilingual_meta present and correct for English input: {meta}")


# ---------------------------------------------------------------------------
# 5. Graceful degradation
# ---------------------------------------------------------------------------

def test_graceful_degradation_no_api_key() -> None:
    """
    When GROQ_API_KEY is explicitly passed as empty string, translate_to_english
    must return the original text unchanged without raising any exception.
    The env-var-level key is bypassed by passing api_key="" directly.
    """
    _section("TEST 5a — Graceful degradation: missing GROQ_API_KEY")

    hindi_text = "शक्ति: 100-150W, वोल्टेज: 230V AC, सुरक्षा: IP65"

    # Pass api_key="" explicitly — multilingual.py treats this as absent key
    # (resolved_key is falsy → falls back immediately without API call)
    result_text, success = translate_to_english(hindi_text, ["Devanagari"], api_key="")

    assert result_text == hindi_text, (
        f"Original text should be returned on missing key.\n"
        f"Expected: {hindi_text}\n"
        f"Got:      {result_text}"
    )
    assert success is False, f"translation_success should be False: {success}"
    print("[OK] Missing API key → original text returned, no exception raised")


def test_graceful_degradation_empty_text() -> None:
    """
    Empty string input must not crash normalize_text or detect_non_english_script.
    """
    _section("TEST 5b — Graceful degradation: empty text")

    text, meta = normalize_text("")
    assert text == "", f"Expected empty string, got: '{text}'"
    assert meta["was_translated"] is False
    assert meta["detected_scripts"] == []
    print("[OK] Empty text handled gracefully by normalize_text")

    is_ne, scripts = detect_non_english_script("")
    assert not is_ne and scripts == []
    print("[OK] Empty text handled gracefully by detect_non_english_script")


def test_graceful_degradation_whitespace_text() -> None:
    """Whitespace-only text must not crash and must return is_non_english=False."""
    _section("TEST 5c — Graceful degradation: whitespace-only text")

    text, meta = normalize_text("   \n\t  \n  ")
    assert meta["was_translated"] is False
    print("[OK] Whitespace-only text handled gracefully")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{SEP}")
    print("  StandardSense — Multilingual NLP Test Suite")
    print(SEP)

    # ── Group 1: Script detection (no API calls) ──────────────────────────
    test_detect_english_text()
    test_detect_devanagari()
    test_detect_tamil()
    test_detect_telugu()
    test_detect_bengali()
    test_detect_gujarati()
    test_detect_mixed_english_hindi()
    test_detect_edge_cases()

    # ── Group 2: Normalization pass-through (no API calls) ────────────────
    test_normalize_passthrough_english()

    # ── Group 5: Graceful degradation (no API calls) ──────────────────────
    # Run before live tests so degradation coverage is confirmed even
    # when GROQ_API_KEY is not available in the environment.
    test_graceful_degradation_no_api_key()
    test_graceful_degradation_empty_text()
    test_graceful_degradation_whitespace_text()

    # ── Group 4d: Meta key contract (no API calls) ────────────────────────
    test_multilingual_meta_always_present()

    # ── Group 3 & 4: Live Groq API tests (skipped if no key) ─────────────
    test_translate_hindi_tender()
    test_pipeline_hindi_full()
    test_pipeline_tamil_snippet()
    test_pipeline_telugu_snippet()

    print(f"\n{SEP}")
    print("  ALL MULTILINGUAL TESTS PASSED")
    print(SEP)
