"""
extractor.py
------------
Rule-based NLP information extraction module for StandardSense (Team A - NLP Extraction).

Extracts structured procurement data from tender text:
- Product / item name
- Technical specifications (list of clauses/requirements)
- Technical parameters (power, IP rating, lifespan, voltage, etc.)
- Explicit Indian Standard codes (e.g., IS 10322, IS 1786, IS 456)
- Consolidated natural-language spec_text for Semantic Search
- Unique spec_id derived from filename or document identifier
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from nlp_extraction.parser import clean_text, extract_text_from_pdf


def extract_product(text: str) -> str:
    """
    Extract the product or item name from tender text.

    Searches across:
    1. Explicit product/item labels (e.g., "Product:", "Item Name:", "Material:")
    2. Procurement phrases (e.g., "Procurement of ...", "Supply of ...")
    3. Tender title labels (e.g., "Tender Title: ...")

    Parameters
    ----------
    text : str
        Cleaned or raw tender text.

    Returns
    -------
    str
        Extracted product name, or empty string if not detected.
    """
    if not text:
        return ""

    # 1. Look for explicit product or item labels
    label_pattern = re.compile(
        r"(?:product(?:\s*name)?|item(?:\s*name)?|material(?:\s*name)?)\s*[:\-–]\s*([^\n\r]+)",
        re.IGNORECASE,
    )
    match = label_pattern.search(text)
    if match:
        val = match.group(1).strip()
        return val.strip('."\'')

    # 2. Look for procurement/supply phrases
    phrase_pattern = re.compile(
        r"(?:procurement\s+of|supply\s+(?:and\s+installation\s+)?of|tender\s+for)\s+([^.\n\r,;]+)",
        re.IGNORECASE,
    )
    match = phrase_pattern.search(text)
    if match:
        val = match.group(1).strip()
        return val.strip('."\'')

    # 3. Look for tender title labels as a fallback
    title_pattern = re.compile(
        r"tender\s+title\s*[:\-–]\s*([^\n\r]+)",
        re.IGNORECASE,
    )
    match = title_pattern.search(text)
    if match:
        val = match.group(1).strip()
        # Clean off trailing keywords like "Procurement" or "Tender"
        cleaned_val = re.sub(r"\s+(?:procurement|tender)$", "", val, flags=re.IGNORECASE)
        return cleaned_val.strip('."\'')

    return ""


def extract_standards(text: str) -> list[str]:
    """
    Extract explicit Indian Standard (IS) codes mentioned in the text.

    Identifies codes such as IS 10322, IS 1786, IS 456, IS 1239, etc.,
    optionally including year specifications (e.g., IS 1786:2008).

    Parameters
    ----------
    text : str
        The input text.

    Returns
    -------
    list[str]
        Deduplicated list of standard codes in standard format (e.g. ['IS 10322']).
    """
    if not text:
        return []

    # Requires uppercase "IS" or "I.S." to avoid matching ordinary English "is"
    pattern = re.compile(
        r"\b(?:IS|I\.S\.)\s*[:\-/]?\s*(\d{2,5}(?:\s*[:\-]\s*\d{4})?)\b"
    )

    matches = pattern.findall(text)
    standards: list[str] = []

    for code_num in matches:
        formatted_code = f"IS {code_num.strip()}"
        if formatted_code not in standards:
            standards.append(formatted_code)

    return standards


def extract_parameters(text: str) -> dict[str, str]:
    """
    Extract key technical parameters into a structured dictionary.

    Extracts:
    - power
    - protection (IP rating)
    - lifespan
    - voltage
    - color_temperature
    - warranty
    - operating_temperature
    - grade
    - material
    - dimensions

    Parameters
    ----------
    text : str
        The input text.

    Returns
    -------
    dict[str, str]
        Dictionary of detected technical parameter names and values.
    """
    if not text:
        return {}

    parameters: dict[str, str] = {}

    # 1. Power (e.g., "100-150W", "100W-150W", "150W", "25 kW")
    # Range pattern first (e.g., "wattage range 100W-150W", "100W-150W", "100-150W", "100 - 150 W")
    power_range = re.search(
        r"\b(\d+)\s*(?:W|kW|MW|Watts?|hp)?\s*[-–]\s*(\d+)\s*(W|kW|MW|Watts?|hp)\b",
        text,
        re.IGNORECASE,
    )
    if power_range:
        start, end, unit = power_range.groups()
        unit_str = unit.upper() if len(unit) <= 2 else unit
        parameters["power"] = f"{start}-{end}{unit_str}"
    else:
        # Labeled with colon/dash: e.g. 'Power: 150W'
        power_label = re.search(
            r"(?:power(?:\s*(?:rating|consumption|range))?|wattage(?:\s*range)?)\s*[:\-–]\s*([^\n\r,;]+)",
            text,
            re.IGNORECASE,
        )
        if power_label:
            val = power_label.group(1).strip()
            m_single = re.search(r"\b(\d+(?:\.\d+)?\s*(?:W|kW|MW|Watts?|hp))\b", val, re.IGNORECASE)
            if m_single:
                parameters["power"] = m_single.group(1).strip()
            else:
                parameters["power"] = val
        else:
            # Labeled without colon but followed by numeric value: e.g. 'wattage 150W'
            power_label_no_colon = re.search(
                r"(?:power(?:\s*(?:rating|consumption|range))?|wattage(?:\s*range)?)\s+(\d+(?:\.\d+)?\s*(?:W|kW|MW|Watts?|hp))\b",
                text,
                re.IGNORECASE,
            )
            if power_label_no_colon:
                parameters["power"] = power_label_no_colon.group(1).strip()
            else:
                # Inline standalone power value: e.g. '150W', '25 kW'
                power_inline = re.search(
                    r"\b(\d+(?:\.\d+)?\s*(?:W|kW|MW|Watts?|hp))\b",
                    text,
                    re.IGNORECASE,
                )
                if power_inline:
                    parameters["power"] = power_inline.group(1).strip()

    # 2. Protection / IP Rating (e.g., "IP65", "IP67")
    protection_label = re.search(
        r"(?:protection(?:\s*rating|\s*class)?|ip\s*rating|ingress\s*protection)\s*[:\-–]\s*([^\n\r,;]+)",
        text,
        re.IGNORECASE,
    )
    if protection_label:
        parameters["protection"] = protection_label.group(1).strip()
    else:
        protection_inline = re.search(r"\b(IP\s*\d{2})\b", text, re.IGNORECASE)
        if protection_inline:
            parameters["protection"] = protection_inline.group(1).replace(" ", "").upper()

    # 3. Lifespan (e.g., "50000 hours", "50,000 hrs")
    lifespan_label = re.search(
        r"(?:lifespan|lifetime|rated\s*life|l70(?:\s*life)?)\s*[:\-–]\s*([^\n\r,;]+)",
        text,
        re.IGNORECASE,
    )
    if lifespan_label:
        parameters["lifespan"] = lifespan_label.group(1).strip()
    else:
        lifespan_inline = re.search(r"\b(\d+[\d,]*\s*(?:hours|hrs|operating\s*hours))\b", text, re.IGNORECASE)
        if lifespan_inline:
            parameters["lifespan"] = lifespan_inline.group(1).strip()

    # 4. Voltage (e.g., "working voltage up to 1100V", "Operating voltage: 230V AC", "220-240 V", "11kV")
    voltage_label = re.search(
        r"(?:operating\s*voltage|rated\s*voltage|input\s*voltage|working\s*voltage|voltage)\s*[:\-–]\s*([^\n\r,;]+)",
        text,
        re.IGNORECASE,
    )
    if voltage_label:
        val = voltage_label.group(1).strip()
        m_volt = re.search(
            r"(\d+(?:\s*[-–]\s*\d+)?\s*(?:V|kV|Volts?)(?:\s*(?:AC|DC))?)",
            val,
            re.IGNORECASE,
        )
        if m_volt:
            parameters["voltage"] = m_volt.group(1).strip()
        else:
            parameters["voltage"] = val
    else:
        inline_label = re.search(
            r"(?:working\s+voltage|operating\s+voltage|rated\s+voltage|voltage)\s+(?:up\s+to\s+)?(\d+(?:\s*[-–]\s*\d+)?\s*(?:V|kV|Volts?)(?:\s*(?:AC|DC))?)",
            text,
            re.IGNORECASE,
        )
        if inline_label:
            parameters["voltage"] = inline_label.group(1).strip()
        else:
            voltage_inline = re.search(
                r"\b(\d+(?:\s*[-–]\s*\d+)?\s*(?:V|kV|Volts?)(?:\s*(?:AC|DC))?)\b",
                text,
                re.IGNORECASE,
            )
            if voltage_inline:
                parameters["voltage"] = voltage_inline.group(1).strip()

    # 5. Color Temperature (e.g., "4000K", "5700 K", "3000K-6500K")
    cct_label = re.search(
        r"(?:color\s*temperature|cct)\s*[:\-–]\s*([^\n\r,;]+)",
        text,
        re.IGNORECASE,
    )
    if cct_label:
        parameters["color_temperature"] = cct_label.group(1).strip()
    else:
        cct_inline = re.search(r"\b(\d{4}\s*K)\b", text, re.IGNORECASE)
        if cct_inline:
            parameters["color_temperature"] = cct_inline.group(1).strip()

    # 6. Warranty (e.g., "5 years", "24 months")
    warranty_label = re.search(
        r"(?:warranty(?:\s*period)?|guarantee)\s*[:\-–]\s*([^\n\r,;]+)",
        text,
        re.IGNORECASE,
    )
    if warranty_label:
        parameters["warranty"] = warranty_label.group(1).strip()
    else:
        warranty_inline = re.search(r"\b(\d+\s*(?:years?|months?)(?:\s*warranty)?)\b", text, re.IGNORECASE)
        if warranty_inline:
            parameters["warranty"] = warranty_inline.group(1).strip()

    # 7. Operating Temperature (e.g., "-10°C to 50°C", "0 to 45 deg C")
    temp_label = re.search(
        r"(?:operating\s*temperature|temperature\s*range)\s*[:\-–]\s*([^\n\r,;]+)",
        text,
        re.IGNORECASE,
    )
    if temp_label:
        parameters["operating_temperature"] = temp_label.group(1).strip()
    else:
        temp_inline = re.search(
            r"([-–]?\d+\s*(?:°\s*C|deg\s*C|C)\s*(?:to|-)\s*[-–]?\d+\s*(?:°\s*C|deg\s*C|C))",
            text,
            re.IGNORECASE,
        )
        if temp_inline:
            parameters["operating_temperature"] = temp_inline.group(1).strip()

    # 8. Grade (e.g., "Fe 500D", "Fe 415", "M25")
    grade_label = re.search(
        r"(?:steel\s*grade|material\s*grade|concrete\s*grade|grade)\s*[:\-–]\s*([^\n\r,;]+)",
        text,
        re.IGNORECASE,
    )
    if grade_label:
        parameters["grade"] = grade_label.group(1).strip()
    else:
        grade_inline = re.search(
            r"\b(Fe\s*500D|Fe\s*415|Fe\s*500|Fe\s*550D|M20|M25|M30|M40|Grade\s+[A-Z0-9]+)\b",
            text,
            re.IGNORECASE,
        )
        if grade_inline:
            parameters["grade"] = grade_inline.group(1).strip()

    # 9. Material (e.g., "die-cast aluminium", "aluminium die-cast", "mild steel", "polycarbonate", "PVC")
    # Only extracted when an explicit material requirement/label is present (e.g. "Material: PVC", "housing material PVC")
    material_label = re.search(
        r"(?:(?:housing|construction|body|insulation|sheath)?\s*material)\s*[:\-–]\s*([^\n\r,;]+)",
        text,
        re.IGNORECASE,
    )
    if material_label:
        parameters["material"] = material_label.group(1).strip()
    else:
        material_prefixed = re.search(
            r"(?:(?:housing|construction|body|insulation|sheath)?\s*material)\s+(?:is\s+|shall\s+be\s+)?([a-zA-Z0-9]+(?:[- ][a-zA-Z0-9]+){0,3})\b",
            text,
            re.IGNORECASE,
        )
        if material_prefixed:
            parameters["material"] = material_prefixed.group(1).strip()

    # 10. Dimensions (e.g., "12mm x 6m", "150mm x 200mm x 50mm")
    dimensions_label = re.search(
        r"(?:dimensions?|physical\s*size|size)\s*[:\-–]\s*([^\n\r,;]+)",
        text,
        re.IGNORECASE,
    )
    if dimensions_label:
        parameters["dimensions"] = dimensions_label.group(1).strip()
    else:
        dimensions_inline = re.search(
            r"\b(\d+(?:\.\d+)?\s*(?:mm|cm|m)\s*[xX×]\s*\d+(?:\.\d+)?\s*(?:mm|cm|m)(?:\s*[xX×]\s*\d+(?:\.\d+)?\s*(?:mm|cm|m))?)\b",
            text,
        )
        if dimensions_inline:
            parameters["dimensions"] = dimensions_inline.group(1).strip()

    return parameters


def extract_specifications(text: str) -> list[str]:
    """
    Extract individual technical specifications or requirement clauses from text.

    Captures bulleted items (-, *, •), numbered items (1., a)), or lines under
    specification headers.

    Parameters
    ----------
    text : str
        The input text.

    Returns
    -------
    list[str]
        List of specification strings.
    """
    if not text:
        return []

    specs: list[str] = []
    lines = text.splitlines()

    # Pattern matching bullet points or numbered lists:
    # e.g., "- ...", "* ...", "• ...", "1. ...", "1) ...", "(1) ...", "a) ..."
    bullet_pattern = re.compile(
        r"^(?:[-*•–—]|(?:\(?\d+[.)]|\(?[a-zA-Z][.)]))\s+(.+)$"
    )

    for line in lines:
        cleaned_line = line.strip()
        if not cleaned_line:
            continue

        match = bullet_pattern.match(cleaned_line)
        if match:
            item = match.group(1).strip()
            if item and item not in specs:
                specs.append(item)

    # Fallback: if no bulleted items were found, capture lines under specification headers
    if not specs:
        in_spec_section = False
        section_headers = re.compile(
            r"^(?:technical\s+specifications?|specifications?|requirements?|scope\s+of\s+work)\s*[:\-–]?",
            re.IGNORECASE,
        )
        for line in lines:
            cleaned_line = line.strip()
            if not cleaned_line:
                continue

            if section_headers.match(cleaned_line):
                in_spec_section = True
                continue

            if in_spec_section:
                # Stop if another distinct section header appears
                if re.match(r"^[A-Z][A-Za-z\s]+:", cleaned_line) and not section_headers.match(cleaned_line):
                    if ":" in cleaned_line and not any(k in cleaned_line.lower() for k in ["power", "voltage", "rating", "is ", "conform"]):
                        in_spec_section = False
                        continue
                if cleaned_line and cleaned_line not in specs:
                    specs.append(cleaned_line)

    return specs


SEMANTIC_QUALIFIERS = {
    "up", "to", "min", "max", "minimum", "maximum", "at", "least",
    "exceeding", "not", "between", "less", "more", "greater", "plus", "minus",
    "approx", "approximately", "class", "type",
}

LABEL_BOILERPLATE = {
    "power", "wattage", "range", "rating", "consumption",
    "voltage", "operating", "working", "rated", "input", "supply",
    "protection", "ip", "class", "ingress",
    "lifespan", "lifetime", "life", "hours", "hrs",
    "color", "temperature", "cct", "temp",
    "warranty", "guarantee", "period",
    "grade", "steel", "concrete",
    "material", "housing", "body", "construction", "insulation", "sheath",
    "dimensions", "dimension", "size", "physical",
}


def _normalize_tokens(text: str) -> set[str]:
    """Normalize text into a set of alphanumeric lowercase tokens, splitting ranges."""
    expanded = re.sub(
        r"(\d+)\s*(?:w|kw|mw|hp|watts?)?\s*[-–]\s*(\d+)\s*(w|kw|mw|hp|watts?)?",
        r"\1 \2 \3",
        text,
        flags=re.IGNORECASE,
    )
    tokens = re.sub(r"[^a-zA-Z0-9]+", " ", expanded).strip().lower().split()
    return set(tokens)


def is_spec_redundant(
    spec_item: str,
    product: str,
    parameters: dict[str, str],
    explicit_standards: list[str],
) -> bool:
    """
    Determine whether a specification clause is already represented by
    product, parameters, or explicit standards without contributing unique
    semantic requirements.
    """
    item_tokens = _normalize_tokens(spec_item)
    item_norm = re.sub(r"[^a-zA-Z0-9]+", " ", spec_item).strip().lower()

    # 1. Redundant if identical to product name
    if product:
        prod_norm = re.sub(r"[^a-zA-Z0-9]+", " ", product).strip().lower()
        if item_norm == prod_norm:
            return True

    # 2. Redundant if it is solely a standard reference (e.g. 'The fixture shall conform to IS 10322.')
    for std in explicit_standards:
        std_num = re.search(r"\d+", std)
        if std_num and std_num.group(0) in item_tokens and any(
            k in item_tokens for k in ["is", "standard", "conform", "conforming", "as", "per"]
        ):
            non_std_tokens = item_tokens - {
                "the", "fixture", "shall", "conform", "conforming", "to",
                "as", "per", "is", "standard", "standards", std_num.group(0).lower(),
            }
            if not non_std_tokens:
                return True

    # 3. Check if captured by an extracted parameter
    for k, v in parameters.items():
        if not v:
            continue
        v_tokens = _normalize_tokens(v)
        if v_tokens and v_tokens.issubset(item_tokens):
            remainder_tokens = item_tokens - v_tokens
            # If remainder has semantic qualifiers like 'up', 'to', 'min', 'max',
            # it conveys critical semantic criteria (e.g., 'working voltage up to 1100V')
            # and is therefore NOT redundant.
            if remainder_tokens & SEMANTIC_QUALIFIERS:
                continue
            # If all remainder words are just boilerplate labels (like 'operating', 'voltage', 'power')
            if remainder_tokens.issubset(LABEL_BOILERPLATE):
                return True

    return False


def build_spec_text(
    product: str,
    parameters: dict[str, str],
    specs: list[str],
    explicit_standards: list[str],
) -> str:
    """
    Combine product, extracted parameters, specifications, and explicit IS standards
    into ONE consolidated natural-language string suitable for semantic search.

    Format:
    "Product, Param1 Value, Param2 Value, ..., Spec1, Spec2, Standard1, Standard2"

    Parameters
    ----------
    product : str
        Extracted product or tender title.
    parameters : dict[str, str]
        Key-value dictionary of extracted technical parameters.
    specs : list[str]
        List of extracted specification bullet points/clauses.
    explicit_standards : list[str]
        List of explicitly cited Indian Standard codes.

    Returns
    -------
    str
        Natural-language specification string for semantic search.
    """
    parts: list[str] = []

    if product:
        parts.append(product.strip())

    if parameters:
        for key, val in parameters.items():
            if not val:
                continue
            val_clean = val.strip()
            key_name = key.replace("_", " ").lower()
            # If value already contains key name (e.g. "working voltage up to 1100V", "Grade Fe 500D")
            if key_name in val_clean.lower():
                parts.append(val_clean)
            else:
                label = key.replace("_", " ").capitalize()
                parts.append(f"{label} {val_clean}")

    # Preserve important specification clauses not already captured in parameters or standards
    if specs:
        for item in specs:
            cleaned_item = item.strip()
            if not cleaned_item:
                continue
            if not is_spec_redundant(cleaned_item, product, parameters, explicit_standards):
                if cleaned_item not in parts:
                    parts.append(cleaned_item)

    if explicit_standards:
        for std in explicit_standards:
            std_clean = std.strip()
            if std_clean and std_clean not in parts:
                parts.append(std_clean)

    return ", ".join(parts)


def extract_from_text(text: str, spec_id: str = "") -> dict[str, Any]:
    """
    Primary extraction entry point. Processes raw text through cleaning and rule-based
    extraction routines.

    Parameters
    ----------
    text : str
        The raw or cleaned text extracted from a procurement/tender document.
    spec_id : str
        Optional identifier for the specification. Defaults to "spec_001" if empty.

    Returns
    -------
    dict[str, Any]
        Structured dictionary containing:
        - "spec_id": str
        - "spec_text": str
        - "product": str
        - "specs": list[str]
        - "parameters": dict[str, str]
        - "explicit_standards": list[str]
    """
    cleaned = clean_text(text)

    product = extract_product(cleaned)
    specs = extract_specifications(cleaned)
    parameters = extract_parameters(cleaned)
    standards = extract_standards(cleaned)
    spec_text = build_spec_text(product, parameters, specs, standards)

    return {
        "spec_id": spec_id or "spec_001",
        "spec_text": spec_text,
        "product": product,
        "specs": specs,
        "parameters": parameters,
        "explicit_standards": standards,
    }


def extract_from_pdf(pdf_path: str, spec_id: str | None = None) -> dict[str, Any]:
    """
    Convenience function to extract structured tender specifications directly from a PDF file.

    Derives spec_id from the PDF filename if not explicitly provided.
    (e.g., "sample_tender_01.pdf" -> "sample_tender_01")

    Parameters
    ----------
    pdf_path : str
        Path to the PDF file on disk.
    spec_id : str | None
        Optional identifier. If omitted, derived from the PDF filename stem.

    Returns
    -------
    dict[str, Any]
        Structured extraction output dictionary.
    """
    if spec_id is None:
        spec_id = Path(pdf_path).stem

    raw_text = extract_text_from_pdf(pdf_path)
    return extract_from_text(raw_text, spec_id=spec_id)