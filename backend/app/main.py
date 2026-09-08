from pathlib import Path
import tempfile
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
        )

        # --------------------------------------------------
        # 3. AMBIGUITY DETECTION
        # --------------------------------------------------

        explicit_standards = extracted.get(
            "explicit_standards",
            [],
        )

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