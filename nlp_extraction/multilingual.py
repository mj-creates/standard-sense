"""
multilingual.py
---------------
Multilingual normalization pre-processor for StandardSense NLP Extraction.

Responsibilities
----------------
1. Detect whether extracted tender text contains non-English scripts
   (Devanagari, Tamil, Telugu, Bengali, Gujarati, Kannada, Malayalam,
   Gurmukhi / Punjabi, Odia, Urdu/Arabic) using Unicode codepoint ranges —
   zero external dependencies, zero network calls for pure-English input.

2. If non-English script is detected, call the Groq LLM to translate and
   normalise the text into structured English while preserving:
   - All numeric values and their units  (e.g. 100-150W, IP65, 230V AC)
   - Indian Standard codes               (e.g. IS 10322)
   - Technical parameter labels in English (power, voltage, protection, …)

3. Return the (possibly translated) text so the existing English regex
   extraction pipeline in extractor.py can run completely unchanged.

Design constraints
------------------
- English-only input  → detect_non_english_script() returns False
                      → translate_to_english() is never called
                      → zero latency overhead, zero API cost

- Non-English input   → single Groq LLM call with a carefully-scoped prompt
                      → on any API error the ORIGINAL text is returned
                        so the pipeline degrades gracefully rather than crashing

- No new required dependencies: uses groq (already in requirements.txt).
  GROQ_API_KEY is read from the environment; absent key → graceful fallback.
"""

from __future__ import annotations

import os
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Unicode script ranges for 12 official Indian scripts  (+ Urdu/Arabic)
# Each tuple is (range_start, range_end, language_name)
# ---------------------------------------------------------------------------
_INDIAN_SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x0900, 0x097F, "Devanagari"),        # Hindi, Marathi, Sanskrit, Nepali
    (0x0980, 0x09FF, "Bengali"),           # Bengali / Assamese
    (0x0A00, 0x0A7F, "Gurmukhi"),          # Punjabi
    (0x0A80, 0x0AFF, "Gujarati"),          # Gujarati
    (0x0B00, 0x0B7F, "Odia"),              # Odia
    (0x0B80, 0x0BFF, "Tamil"),             # Tamil
    (0x0C00, 0x0C7F, "Telugu"),            # Telugu
    (0x0C80, 0x0CFF, "Kannada"),           # Kannada
    (0x0D00, 0x0D7F, "Malayalam"),         # Malayalam
    (0x0600, 0x06FF, "Arabic/Urdu"),       # Urdu (uses Arabic script)
    (0x0750, 0x077F, "Arabic Supplement"), # Arabic Supplement (Urdu variants)
]

# Minimum fraction of non-ASCII characters in the text that triggers translation.
# Set low (2 %) so even a mixed-language PDF (mostly English, some Hindi headers)
# is caught and normalised.
_NON_ENGLISH_CHAR_THRESHOLD: float = 0.02

# Groq model to use for translation — same account-verified model as search.py
_GROQ_TRANSLATION_MODEL: str = "groq/compound-mini"

# Maximum tokens for the translated output (tender texts are typically ≤ 1 500 words)
_MAX_TRANSLATION_TOKENS: int = 2048


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def detect_non_english_script(text: str) -> tuple[bool, list[str]]:
    """
    Detect whether *text* contains characters from any of the 12 supported
    Indian scripts (Devanagari, Tamil, Telugu, Bengali, Gujarati, Kannada,
    Malayalam, Gurmukhi, Odia, Urdu/Arabic).

    Returns
    -------
    tuple[bool, list[str]]
        (is_non_english, detected_script_names)

        is_non_english  – True if the text meets the threshold for non-English script
        detected_script_names – list of script names found (empty if purely English)

    Notes
    -----
    - Pure ASCII / Latin text → returns (False, []) instantly.
    - Mixed documents (e.g., English tender with Hindi section headers) are
      detected as non-English so they go through translation.
    - Numeric characters, punctuation, and whitespace are ignored.
    """
    if not text:
        return False, []

    total_chars = len([c for c in text if not c.isspace()])
    if total_chars == 0:
        return False, []

    # Fast-path: if every character is ASCII, skip unicode range checks entirely
    if all(ord(c) < 128 for c in text):
        return False, []

    script_hit_counts: dict[str, int] = {}
    non_english_count = 0

    for char in text:
        cp = ord(char)
        if cp < 128:          # ASCII — skip
            continue
        for (start, end, name) in _INDIAN_SCRIPT_RANGES:
            if start <= cp <= end:
                script_hit_counts[name] = script_hit_counts.get(name, 0) + 1
                non_english_count += 1
                break           # a character belongs to only one range

    fraction = non_english_count / total_chars
    detected_scripts = sorted(script_hit_counts.keys())

    is_non_english = fraction >= _NON_ENGLISH_CHAR_THRESHOLD and bool(detected_scripts)
    return is_non_english, detected_scripts


# ---------------------------------------------------------------------------
# Groq translation
# ---------------------------------------------------------------------------

_TRANSLATION_SYSTEM_PROMPT = """\
You are a precise technical translator for Indian government procurement documents.
Your task is to translate the provided tender/procurement text into clear, structured English.

Translation rules (follow strictly):
1. Preserve ALL numeric values exactly as written (e.g. 100-150W, 50000, 230).
2. Preserve ALL units exactly (W, kW, V, kV, Hz, mm, cm, m, kg, °C, IP65, etc.).
3. Preserve ALL Indian Standard codes exactly (e.g. IS 10322, IS 1786:2008).
4. Convert ALL parameter labels to their standard English equivalents:
   - शक्ति / वाट / बिजली → Power
   - वोल्टेज / विद्युत दाब → Voltage
   - सुरक्षा / आईपी रेटिंग → Protection
   - जीवनकाल / आयु → Lifespan
   - वारंटी / गारंटी → Warranty
   - तापमान → Temperature / Operating Temperature
   - सामग्री → Material
   - आयाम / आकार → Dimensions
   - उत्पाद / सामान → Product
   - विशिष्टताएं → Specifications
   (Apply the same logic for Tamil, Telugu, Bengali, Gujarati, Kannada, Malayalam, Punjabi, Odia, Urdu)
5. Output ONLY the translated text. No explanations, no preamble, no markdown.
6. Maintain the same structural format (bullet points, numbered lists, section headers) as the input.
7. If a sentence or clause is already in English, reproduce it verbatim.
"""

_TRANSLATION_USER_TEMPLATE = """\
Translate the following Indian government tender text to English. \
Detected script(s): {scripts}. Follow all translation rules exactly.

--- TENDER TEXT BEGIN ---
{text}
--- TENDER TEXT END ---
"""


def translate_to_english(
    text: str,
    detected_scripts: Optional[list[str]] = None,
    api_key: Optional[str] = None,
) -> tuple[str, bool]:
    """
    Translate *text* from Indian regional language(s) to English using the
    Groq LLM.

    Parameters
    ----------
    text : str
        Raw tender text (may be fully or partially non-English).
    detected_scripts : list[str] | None
        Script names returned by detect_non_english_script(); used in the
        prompt to help the model. If None, uses ["Unknown Indian script"].
    api_key : str | None
        Groq API key. Falls back to the GROQ_API_KEY environment variable.

    Returns
    -------
    tuple[str, bool]
        (translated_text, translation_succeeded)

        translated_text      – English text if translation succeeded,
                               original text on any error (graceful fallback)
        translation_succeeded – True if the LLM call returned a valid response
    """
    resolved_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
    if not resolved_key:
        # No API key — return original text unchanged, log a warning
        _warn("GROQ_API_KEY not set; skipping multilingual translation.")
        return text, False

    scripts_str = ", ".join(detected_scripts) if detected_scripts else "Unknown Indian script"
    user_message = _TRANSLATION_USER_TEMPLATE.format(
        scripts=scripts_str,
        text=text.strip(),
    )

    try:
        from groq import Groq  # imported here to keep module lightweight when not used

        client = Groq(api_key=resolved_key)
        response = client.chat.completions.create(
            model=_GROQ_TRANSLATION_MODEL,
            messages=[
                {"role": "system", "content": _TRANSLATION_SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.1,        # near-deterministic for technical translation
            max_tokens=_MAX_TRANSLATION_TOKENS,
        )
        translated = response.choices[0].message.content.strip()

        if not translated:
            _warn("Groq returned an empty translation; using original text.")
            return text, False

        return translated, True

    except Exception as exc:  # noqa: BLE001
        _warn(f"Groq translation failed ({type(exc).__name__}: {exc}); using original text.")
        return text, False


# ---------------------------------------------------------------------------
# Unified normalisation entry point (called by extractor.py)
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> tuple[str, dict]:
    """
    Main entry point for the multilingual normalisation pre-processor.

    Detects whether *text* contains supported non-English Indian scripts and,
    if so, calls the Groq LLM to translate it to English before returning.
    For English-only input this function is a zero-cost pass-through.

    Parameters
    ----------
    text : str
        Raw text extracted from a tender PDF by PyMuPDF.

    Returns
    -------
    tuple[str, dict]
        (normalized_text, metadata)

        normalized_text – English text (translated if needed, original otherwise)
        metadata        – diagnostic dict with keys:
                          "was_translated"     : bool
                          "detected_scripts"   : list[str]
                          "translation_success": bool
                          "original_language"  : str   (comma-joined script names or "English")

    Examples
    --------
    English input (no API call made):
        normalize_text("Supply of LED street light 100-150W IP65")
        → ("Supply of LED street light 100-150W IP65",
           {"was_translated": False, "detected_scripts": [], ...})

    Hindi input (Groq called once):
        normalize_text("एलईडी स्ट्रीट लाइट की आपूर्ति, शक्ति: 100-150W")
        → ("Supply of LED Street Light, Power: 100-150W",
           {"was_translated": True, "detected_scripts": ["Devanagari"], ...})
    """
    is_non_english, detected_scripts = detect_non_english_script(text)

    if not is_non_english:
        return text, {
            "was_translated":      False,
            "detected_scripts":    [],
            "translation_success": False,
            "original_language":   "English",
        }

    translated_text, success = translate_to_english(text, detected_scripts)

    return translated_text, {
        "was_translated":      True,
        "detected_scripts":    detected_scripts,
        "translation_success": success,
        "original_language":   ", ".join(detected_scripts) if detected_scripts else "Unknown",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _warn(message: str) -> None:
    """Emit a non-fatal warning to stderr without importing logging."""
    import sys
    print(f"[multilingual] WARNING: {message}", file=sys.stderr)
