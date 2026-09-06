"""
parser.py
---------
PDF text extraction and text cleaning utilities for StandardSense (Team A - NLP Extraction).

Provides:
- extract_text_from_pdf: Extracts text sequentially from all pages of a PDF using PyMuPDF.
- clean_text: Cleans and normalizes extracted text while strictly preserving technical specifications.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
import pymupdf


# Regex pattern to identify lines that contain only page numbers or simple page markers.
# Matches forms such as: "1", "Page 1", "Page 1 of 12", "1 / 15", "- 3 -", "(4)", "[5]"
_PAGE_NUMBER_PATTERN = re.compile(
    r"^(?:page\s+\d+(?:\s*(?:of|/)\s*\d+)?|\d+\s*(?:of|/)\s*\d+|[-–—]\s*\d+\s*[-–—]|\d+|\(\d+\)|\[\d+\])$",
    re.IGNORECASE,
)

# Regex to normalize horizontal whitespace (spaces, tabs, non-breaking spaces)
_HORIZONTAL_WHITESPACE_PATTERN = re.compile(r"[\t\u00A0\u1680\u2000-\u200a\u202f\u205f\u3000 ]+")


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text content from every page of a PDF file in sequential page order.

    Parameters
    ----------
    pdf_path : str
        The path to the PDF file on disk.

    Returns
    -------
    str
        Combined raw text content of the entire PDF, preserving page order.

    Raises
    ------
    FileNotFoundError
        If the file does not exist at the specified path.
    ValueError
        If the path points to a directory rather than a file.
    RuntimeError
        If PyMuPDF fails to open or read the PDF file.
    """
    path_obj = Path(pdf_path)

    if not path_obj.exists():
        raise FileNotFoundError(f"PDF file not found: '{pdf_path}'")

    if not path_obj.is_file():
        raise ValueError(f"Specified path is not a file: '{pdf_path}'")

    try:
        doc = pymupdf.open(str(path_obj))
    except Exception as exc:
        raise RuntimeError(f"Unable to open PDF file at '{pdf_path}': {exc}") from exc

    page_texts: list[str] = []
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if text:
                page_texts.append(text)
    except Exception as exc:
        raise RuntimeError(f"Error reading pages from PDF '{pdf_path}': {exc}") from exc
    finally:
        doc.close()

    return "\n\n".join(page_texts)


def clean_text(text: str) -> str:
    """
    Clean and normalize extracted document text for downstream NLP processing.

    Cleaning steps:
    - Normalizes non-standard and excessive horizontal whitespace.
    - Removes lines that consist solely of page numbers or page indicators.
    - Collapses multiple consecutive blank lines down to a single blank line.
    - Strictly preserves technical data, including model/grade numbers (e.g., Fe 500D, IP65),
      ranges and ratings (e.g., 100-150W, 50000 hours), standards (e.g., IS 1786),
      percentages, dimensions, and engineering units.

    Parameters
    ----------
    text : str
        The raw extracted text string.

    Returns
    -------
    str
        The cleaned and normalized text.
    """
    if not text:
        return ""

    lines = text.splitlines()
    cleaned_lines: list[str] = []

    for line in lines:
        # Normalize excessive horizontal whitespace within each line
        normalized_line = _HORIZONTAL_WHITESPACE_PATTERN.sub(" ", line).strip()

        # Check if line is empty
        if not normalized_line:
            # Avoid consecutive empty lines
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        # Check and skip obvious standalone page-number lines
        if _PAGE_NUMBER_PATTERN.match(normalized_line):
            continue

        cleaned_lines.append(normalized_line)

    result = "\n".join(cleaned_lines)

    # Collapse any remaining clusters of 3 or more consecutive newlines into 2
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()
