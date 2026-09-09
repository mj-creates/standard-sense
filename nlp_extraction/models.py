"""
models.py
---------
Data models and schemas for StandardSense (Team A - NLP Extraction).

Defines ExtractionResult dataclass representing the structured and semantic-search-ready
output of tender specification extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ExtractionResult:
    """
    Data model representing the extraction output for a procurement specification.

    Attributes
    ----------
    spec_id : str
        Unique identifier derived from the source tender filename or document ID.
    spec_text : str
        Consolidated natural-language specification string suitable for semantic search.
    product : str
        Detected product, item name, or procurement subject.
    specs : List[str]
        List of individual extracted specification clauses/bullet points.
    parameters : Dict[str, str]
        Key-value dictionary of extracted technical parameters (e.g., power, IP rating).
    explicit_standards : List[str]
        List of explicit Indian Standard (IS) codes detected in the document.
    """

    spec_id: str = ""
    spec_text: str = ""
    product: str = ""
    specs: List[str] = field(default_factory=list)
    parameters: Dict[str, str] = field(default_factory=dict)
    explicit_standards: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the ExtractionResult instance to a standard dictionary representation.

        Returns
        -------
        Dict[str, Any]
            Dictionary with exact keys for semantic search and compliance/ranking consumers.
        """
        return {
            "spec_id": self.spec_id,
            "spec_text": self.spec_text,
            "product": self.product,
            "specs": list(self.specs),
            "parameters": dict(self.parameters),
            "explicit_standards": list(self.explicit_standards),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExtractionResult:
        """
        Create an ExtractionResult instance from a dictionary payload.

        Parameters
        ----------
        data : Dict[str, Any]
            Raw dictionary containing extraction fields.

        Returns
        -------
        ExtractionResult
            Instantiated dataclass.
        """
        return cls(
            spec_id=data.get("spec_id", ""),
            spec_text=data.get("spec_text", ""),
            product=data.get("product", ""),
            specs=data.get("specs", []),
            parameters=data.get("parameters", {}),
            explicit_standards=data.get("explicit_standards", []),
        )