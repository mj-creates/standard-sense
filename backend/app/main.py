from pathlib import Path
import tempfile
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Any
from pydantic import BaseModel, Field

from backend.app.auth.router import router as auth_router
from rag_feedback.rag.llm import get_llm

# Officer History router (isolated feature — does not touch auth or search)
from backend.app.officer_history import router as officer_history_router

from nlp_extraction.extractor import extract_from_pdf

from semantic_search.search import (
    semantic_search,
    is_ambiguous,
    generate_clarifying_question,
)

from compliance_ranking.ranking_engine import (
    rank_recommendations,
)

from rag_feedback.rag.rag_engine import (
    generate_rag_response,
)


app = FastAPI(
    title="StandardSense API",
    description="Backend API for tender specification analysis",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")

# Register the officer history router (prefix: /api/officer-history)
app.include_router(officer_history_router)


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "StandardSense backend is running",
    }


def _compute_mandatory_fields(
    recommendations: list[dict],
) -> dict:
    """
    Compute the top-level mandatory compliance summary
    from the highest-ranked recommendation.
    """

    if not recommendations:
        return {
            "is_mandatory_compliant": False,
            "mandatory_failed_fields": [],
            "advisory_failed_fields": [],
        }

    top = recommendations[0]

    status = top.get(
        "compliance_status",
        "unknown",
    )

    failed = top.get(
        "failed_fields",
        [],
    )

    missing = top.get(
        "missing_fields",
        [],
    )

    return {
        "is_mandatory_compliant": (
            status == "compliant"
        ),
        "mandatory_failed_fields": list(
            failed
        ),
        "advisory_failed_fields": list(
            missing
        ),
    }


@app.post("/process-tender")
async def process_tender(
    file: UploadFile = File(...),
    department_override: str = Form(None),
):
    """
    Process a tender specification PDF through
    the complete StandardSense pipeline.

    Pipeline:
        1. NLP Extraction
        2. Semantic Search
        3. Ambiguity Detection
        4. Compliance Ranking
        5. RAG Explanation

    Feature 3:
        Semantic search retrieves 8 candidates.

        Top 5:
            Existing recommendations

        Next 3:
            also_considered

        This is purely additive and does not change
        the existing top 5 recommendation behavior.
    """

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file was uploaded.",
        )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF file.",
        )

    temp_path = None

    try:
        # Read uploaded file.
        file_content = await file.read()

        if not file_content:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Uploaded file is empty. "
                    "Please upload a valid PDF."
                ),
            )

        # Save uploaded PDF temporarily.
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf",
        ) as temp_file:

            temp_file.write(file_content)
            temp_path = temp_file.name

        # --------------------------------------------------
        # 1. NLP EXTRACTION
        # --------------------------------------------------

        extracted = extract_from_pdf(
            temp_path
        )

        original_stem = Path(
            file.filename
        ).stem

        extracted["spec_id"] = original_stem

        spec_id = original_stem

        spec_text = extracted.get(
            "spec_text",
            "",
        )

        spec_parameters = extracted.get(
            "parameters",
            {},
        )
        
        department = department_override or extracted.get("department")

        # --------------------------------------------------
        # Validate extracted specification
        # --------------------------------------------------

        if not spec_text:

            page_count_hint = ""

            try:
                import pymupdf

                doc = pymupdf.open(
                    temp_path
                )

                total_pages = len(doc)

                text_pages = sum(
                    1
                    for page in doc
                    if page.get_text().strip()
                )

                doc.close()

                if text_pages == 0:
                    page_count_hint = (
                        f" The uploaded file appears "
                        f"to be a scanned or image-only "
                        f"PDF ({total_pages} page(s), "
                        f"0 with selectable text). "
                        f"Please upload a PDF with a "
                        f"text layer, or use OCR software "
                        f"first."
                    )

            except Exception:
                pass

            raise HTTPException(
                status_code=422,
                detail=(
                    "Could not extract a specification "
                    "from the PDF."
                    + page_count_hint
                ),
            )

        # --------------------------------------------------
        # 2. SEMANTIC SEARCH
        # --------------------------------------------------
        #
        # Feature 3 requires more candidates than the
        # existing top 5 recommendations.
        #
        # 8 candidates are retrieved:
        #   5 -> recommendations
        #   3 -> also_considered
        #

        semantic_results = semantic_search(
            spec_text,
            top_k=8,
            department=department,
        )

        # --------------------------------------------------
        # 3. AMBIGUITY DETECTION
        # --------------------------------------------------

        explicit_standards = extracted.get(
            "explicit_standards",
            [],
        )

        # --------------------------------------------------
        # FEATURE A: OUT-OF-SCOPE DETECTION
        # Threshold set to 1.20. Real good matches are 0.67-0.85.
        # Real bad matches (e.g. wooden chair) are ~1.57.
        # Halfway between worst good (0.85) and best bad (1.57) is ~1.21, so 1.20 is a safe threshold.
        # --------------------------------------------------
        if semantic_results and not explicit_standards:
            top_score = semantic_results[0].get("l2_score", 0.0)
            if top_score > 1.20:
                return {
                    "status": "out_of_scope",
                    "filename": file.filename,
                    "message": "No confident match found in our current database of 44 electrical/ lighting standards. This product may fall outside current coverage."
                }

        if (
            is_ambiguous(semantic_results)
            and not explicit_standards
        ):

            question = generate_clarifying_question(
                spec_text,
                semantic_results,
            )

            candidates = [
                {
                    "is_code": result["is_code"],
                    "title": result["title"],
                    "description": result["description"],
                    "score": result["l2_score"],
                }
                for result in semantic_results
            ]

            return {
                "status": "needs_clarification",
                "filename": file.filename,
                "question": question,
                "candidates": candidates,
            }

        # --------------------------------------------------
        # 4. COMPLIANCE RANKING
        # --------------------------------------------------

        ranked_results = rank_recommendations(
            spec_id=spec_id,
            spec_text=spec_text,
            spec_parameters=spec_parameters,
            semantic_results=semantic_results,
        )

        # --------------------------------------------------
        # TOP-LEVEL MANDATORY COMPLIANCE SUMMARY
        # --------------------------------------------------

        mandatory_summary = (
            _compute_mandatory_fields(
                ranked_results.get(
                    "recommendations",
                    [],
                )
            )
        )

        # --------------------------------------------------
        # 5. RAG EXPLANATION
        # --------------------------------------------------

        rag_response = generate_rag_response(
            ranked_results
        )

        # --------------------------------------------------
        # FINAL RESPONSE
        # --------------------------------------------------

        return {
            "status": "ok",
            "filename": file.filename,

            "is_mandatory_compliant": (
                mandatory_summary[
                    "is_mandatory_compliant"
                ]
            ),

            "mandatory_failed_fields": (
                mandatory_summary[
                    "mandatory_failed_fields"
                ]
            ),

            "advisory_failed_fields": (
                mandatory_summary[
                    "advisory_failed_fields"
                ]
            ),

            "extraction": extracted,

            "ranking": ranked_results,

            "rag": rag_response,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Error processing tender: {str(e)}"
            ),
        )

    finally:

        # Remove temporary PDF.
        if temp_path:

            import time

            for attempt in range(3):

                try:

                    Path(
                        temp_path
                    ).unlink(
                        missing_ok=True
                    )

                    break

                except (
                    PermissionError,
                    OSError,
                ):

                    if attempt < 2:
                        time.sleep(0.2)


# --------------------------------------------------
# AUTO-FIX ENDPOINT
# --------------------------------------------------

class AutoFixRequest(BaseModel):
    spec_text: str
    is_code: str
    title: str
    failed_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


@app.post("/auto-fix")
def auto_fix(payload: AutoFixRequest):
    """
    Rewrite a non-compliant tender specification to meet standard requirements.
    """
    if not payload.spec_text or not payload.spec_text.strip():
        raise HTTPException(
            status_code=400,
            detail="spec_text must not be empty.",
        )

    if not payload.is_code or not payload.is_code.strip():
        raise HTTPException(
            status_code=400,
            detail="is_code must not be empty.",
        )

    if not payload.title or not payload.title.strip():
        raise HTTPException(
            status_code=400,
            detail="title must not be empty.",
        )

    failed_valid = [
        str(f).strip()
        for f in payload.failed_fields
        if str(f).strip()
    ]
    missing_valid = [
        str(m).strip()
        for m in payload.missing_fields
        if str(m).strip()
    ]

    if not failed_valid and not missing_valid:
        raise HTTPException(
            status_code=400,
            detail="At least one failed or missing field must be present.",
        )

    failed_str = ", ".join(failed_valid) if failed_valid else "None"
    missing_str = ", ".join(missing_valid) if missing_valid else "None"

    prompt = (
        "You are helping a procurement officer fix a non-compliant tender specification.\n\n"
        "Original tender specification text:\n"
        f'"{payload.spec_text.strip()}"\n\n'
        f"This tender is being checked against {payload.is_code.strip()} - {payload.title.strip()}.\n"
        f"The following fields FAILED to meet requirements: {failed_str}\n"
        f"The following fields are MISSING entirely: {missing_str}\n\n"
        "Rewrite the tender specification text so that:\n"
        "1. Everything that was already correct stays exactly as it was\n"
        "2. The failed fields are corrected to meet the standard's requirements\n"
        "3. The missing fields are added with reasonable, standard-compliant values\n"
        "4. The output reads naturally as a tender specification, not a bullet list\n\n"
        "Return ONLY the rewritten specification text, nothing else."
    )

    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        content = response.content

        if isinstance(content, list):
            corrected_text = "".join(str(part) for part in content).strip()
        else:
            corrected_text = str(content).strip()

        corrected_text = (
            corrected_text.replace("\u202f", " ")
            .replace("\u00a0", " ")
            .replace("\u2011", "-")
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Auto-Fix LLM request failed. Please try again.",
        )

    if not corrected_text:
        raise HTTPException(
            status_code=502,
            detail="Auto-Fix returned an empty specification.",
        )

    return {
        "status": "ok",
        "corrected_specification": corrected_text,
    }


# --------------------------------------------------
# COMPLIANCE ANALYSIS ENDPOINT
# --------------------------------------------------

class ComplianceAnalysisRequest(BaseModel):
    spec_parameters: dict[str, Any] = Field(default_factory=dict)
    is_codes: list[str] = Field(default_factory=list)
    spec_id: str = Field(default="")
    spec_text: str = Field(default="")

ComplianceAnalysisRequest.model_rebuild()


@app.post("/compliance-analysis")
def compliance_analysis(payload: ComplianceAnalysisRequest):
    """
    Generate comprehensive compliance analysis:
    - Compliance percentage
    - Gap summary (critical & advisory)
    - Key risks & procurement recommendations
    Calls existing check_compliance() and _REQUIREMENTS from compliance_ranking.
    """
    from compliance_ranking.compliance_checker import check_compliance, _REQUIREMENTS

    try:
        req_path = PROJECT_ROOT / "compliance_ranking" / "mock_requirements.json"
        with open(req_path, "r", encoding="utf-8") as f:
            raw_meta = json.load(f)
            title_map = {entry["is_code"]: entry.get("title", "") for entry in raw_meta}
    except Exception:
        title_map = {}

    def _format_rule_req(rule: dict) -> str:
        if not rule:
            return "Required specification"
        if "min" in rule and "max" in rule:
            return f"Range: {rule['min']} to {rule['max']}"
        if "min" in rule:
            return f"Min threshold: {rule['min']}"
        if "max" in rule:
            return f"Max ceiling: {rule['max']}"
        if "options" in rule:
            return f"Allowed options: {', '.join(str(o) for o in rule['options'])}"
        if "pattern" in rule:
            return f"Format: {rule['pattern']}"
        if rule.get("required"):
            return "Mandatory specification required"
        return "Compliant parameter specification"

    spec_parameters = payload.spec_parameters or {}
    is_codes = [str(c).strip() for c in payload.is_codes if str(c).strip()]

    # If no specific IS codes provided, use top available from requirements
    if not is_codes:
        is_codes = list(_REQUIREMENTS.keys())[:5]

    standards_analysis = []
    all_gaps = []
    all_passed_fields = set()
    all_failed_fields = set()
    all_missing_fields = set()
    total_checks = 0
    total_passed = 0

    for is_code in is_codes:
        comp = check_compliance(spec_parameters, is_code)
        reqs = _REQUIREMENTS.get(is_code, {})
        title = title_map.get(is_code, f"BIS Standard {is_code}")

        passed = comp.get("passed_fields", [])
        failed = comp.get("failed_fields", [])
        missing = comp.get("missing_fields", [])
        mandatory_failed = comp.get("mandatory_failed_fields", [])
        advisory_failed = comp.get("advisory_failed_fields", [])
        is_mand_comp = comp.get("is_mandatory_compliant", False)
        status = comp.get("status", "unknown")

        num_rules = len(reqs) if reqs else (len(passed) + len(failed) + len(missing))
        std_pct = round((len(passed) / num_rules * 100), 1) if num_rules > 0 else 0.0

        total_checks += num_rules
        total_passed += len(passed)
        all_passed_fields.update(passed)
        all_failed_fields.update(failed)
        all_missing_fields.update(missing)

        # Build gaps for this standard
        std_gaps = []
        for f in failed:
            rule = reqs.get(f, {})
            is_mand = bool(rule.get("mandatory", True))
            std_gaps.append({
                "field": f,
                "type": "failed",
                "severity": "critical" if is_mand else "advisory",
                "is_code": is_code,
                "requirement": _format_rule_req(rule),
                "found_value": str(spec_parameters.get(f, "Non-compliant value")),
                "rationale": rule.get("rationale", "Parameter failed technical threshold requirement"),
            })

        for f in missing:
            rule = reqs.get(f, {})
            is_mand = bool(rule.get("mandatory", True))
            std_gaps.append({
                "field": f,
                "type": "missing",
                "severity": "critical" if is_mand else "advisory",
                "is_code": is_code,
                "requirement": _format_rule_req(rule),
                "found_value": "Absent / Not specified",
                "rationale": rule.get("rationale", "Mandatory technical parameter missing from tender"),
            })

        all_gaps.extend(std_gaps)

        standards_analysis.append({
            "is_code": is_code,
            "title": title,
            "status": status,
            "compliance_percentage": std_pct,
            "is_mandatory_compliant": is_mand_comp,
            "passed_fields": passed,
            "failed_fields": failed,
            "missing_fields": missing,
            "mandatory_failed_fields": mandatory_failed,
            "advisory_failed_fields": advisory_failed,
            "total_requirements": num_rules,
            "gaps": std_gaps,
        })

    # Primary standard (first in list)
    primary = standards_analysis[0] if standards_analysis else {}
    primary_pct = primary.get("compliance_percentage", 0.0) if primary else 0.0
    overall_pct = round((total_passed / total_checks * 100), 1) if total_checks > 0 else 0.0

    critical_gaps = [g for g in all_gaps if g["severity"] == "critical"]
    advisory_gaps = [g for g in all_gaps if g["severity"] == "advisory"]

    # Key Risks generation
    key_risks = []
    primary_is_code = primary.get("is_code", "BIS Standard")

    if critical_gaps:
        crit_fields = list(dict.fromkeys([g["field"] for g in critical_gaps]))
        key_risks.append({
            "title": "Statutory & Legal Non-Compliance Risk",
            "level": "HIGH",
            "category": "Regulatory",
            "description": f"Tender specification violates mandatory technical requirements for {', '.join(crit_fields[:3])}.",
            "impact": "Risk of formal audit objections, supplier bid disqualification, or cancellation under mandatory BIS Quality Control Orders (QCO).",
            "mitigation": f"Incorporate mandatory limits for {', '.join(crit_fields[:3])} in the tender scope before issuing the RFP.",
        })

    if advisory_gaps:
        adv_fields = list(dict.fromkeys([g["field"] for g in advisory_gaps]))
        key_risks.append({
            "title": "Operational Scope Ambiguity Risk",
            "level": "MEDIUM",
            "category": "Operational",
            "description": f"Advisory specifications ({', '.join(adv_fields[:3])}) are absent or substandard in the tender document.",
            "impact": "Vendors may supply lower-tier components leading to early degradation, higher maintenance costs, or contractual disputes.",
            "mitigation": "Clarify lifecycle, warranty, and environmental endurance requirements in the tender technical schedule.",
        })

    if not critical_gaps and not advisory_gaps:
        key_risks.append({
            "title": "Low Procurement Risk",
            "level": "LOW",
            "category": "Compliance",
            "description": f"Specification fully satisfies all checked safety, operational, and statutory criteria under {primary_is_code}.",
            "impact": "Tender is legally defensible and adheres to central procurement guidelines.",
            "mitigation": "Ensure post-delivery inspection mandates BIS ISI-marked / certified verification documentation from the winning bidder.",
        })
    elif not critical_gaps:
        key_risks.append({
            "title": "Statutory Compliance Satisfied",
            "level": "LOW",
            "category": "Safety & Statutory",
            "description": f"All core safety and mandatory requirements under {primary_is_code} are completely satisfied.",
            "impact": "No statutory violation under current BIS standards.",
            "mitigation": "Address secondary advisory recommendations to optimize total cost of ownership.",
        })

    return {
        "status": "ok",
        "spec_id": payload.spec_id,
        "primary_standard": primary_is_code,
        "primary_title": primary.get("title", ""),
        "primary_compliance_percentage": primary_pct,
        "overall_compliance_percentage": overall_pct,
        "is_mandatory_compliant": primary.get("is_mandatory_compliant", False),
        "compliance_status": primary.get("status", "unknown"),
        "metrics": {
            "standards_evaluated": len(standards_analysis),
            "total_parameters_checked": total_checks,
            "total_passed": total_passed,
            "total_failed": len(all_failed_fields),
            "total_missing": len(all_missing_fields),
            "total_gaps": len(all_gaps),
            "critical_gaps_count": len(critical_gaps),
            "advisory_gaps_count": len(advisory_gaps),
        },
        "gap_summary": {
            "total_gaps": len(all_gaps),
            "critical_count": len(critical_gaps),
            "advisory_count": len(advisory_gaps),
            "critical_gaps": critical_gaps,
            "advisory_gaps": advisory_gaps,
            "all_gaps": all_gaps,
        },
        "key_risks": key_risks,
        "standards_breakdown": standards_analysis,
    }
