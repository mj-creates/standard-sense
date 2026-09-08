from pathlib import Path
import tempfile
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from nlp_extraction.extractor import extract_from_pdf
from semantic_search.search import semantic_search, is_ambiguous, generate_clarifying_question
from compliance_ranking.ranking_engine import rank_recommendations
from rag_feedback.rag.rag_engine import generate_rag_response


# --------------------------------------------------
# FastAPI application
# --------------------------------------------------

app = FastAPI(
    title="StandardSense API",
    description="Backend API for tender specification analysis",
    version="1.0.0",
)


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # must be False when allow_origins=["*"] — browsers
                               # reject credentialed requests to wildcard origins
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "StandardSense backend is running"
    }


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _compute_mandatory_fields(recommendations: list[dict]) -> dict:
    """
    Compute top-level mandatory compliance summary from the ranked recommendations list.

    Looks at the #1 ranked recommendation (highest compliance tier + best semantic
    score) and surfaces its field breakdown as the primary mandatory compliance verdict
    for the entire response.  All fields reported as 'failed' by the compliance checker
    are classified as mandatory failures; all 'missing' fields are classified as
    advisory gaps (present in the standard's rules but absent from the tender spec —
    they may or may not be required depending on procurement context).

    Returns
    -------
    dict with keys:
        is_mandatory_compliant   : bool   — True only when top rec is fully compliant
        mandatory_failed_fields  : list   — fields that actively failed a rule check
        advisory_failed_fields   : list   — fields absent from spec (missing, not failed)
    """
    if not recommendations:
        return {
            "is_mandatory_compliant": False,
            "mandatory_failed_fields": [],
            "advisory_failed_fields": [],
        }

    top = recommendations[0]
    status = top.get("compliance_status", "unknown")
    failed  = top.get("failed_fields",  [])
    missing = top.get("missing_fields", [])

    return {
        "is_mandatory_compliant":  status == "compliant",
        "mandatory_failed_fields": list(failed),   # active rule violations
        "advisory_failed_fields":  list(missing),  # fields absent from spec
    }


# --------------------------------------------------
# Process Tender
# --------------------------------------------------

@app.post("/process-tender")
async def process_tender(file: UploadFile = File(...)):
    """
    Process a tender specification PDF through the full StandardSense pipeline.

    Request
    -------
    Content-Type : multipart/form-data
    Field        : file  (required) — the tender specification PDF

    Pipeline
    --------
    1. NLP Extraction       — extracts product, parameters, IS codes from PDF text
    2. Semantic Search      — finds top-N matching IS standards via FAISS + embeddings
    3. Ambiguity Detection  — if results are ambiguous AND no explicit IS codes
                              were cited in the tender, returns clarification request.
                              Bypassed when the tender explicitly names a standard
                              (e.g. "IS 10322") — the query is unambiguous.
    4. Compliance Ranking   — checks each candidate against mock_requirements.json rules
                              and sorts by (compliance_tier, semantic_score)
    5. RAG Explanation      — Groq LLM generates per-standard explanation (parallel,
                              timeout=10s per call; falls back to template on failure)

    Response — Confident path (HTTP 200)
    ------------------------------------
    {
        "status": "ok",
        "filename": str,
        "is_mandatory_compliant":  bool,    // True iff top recommendation is compliant
        "mandatory_failed_fields": [str],   // fields that FAILED a rule check (top rec)
        "advisory_failed_fields":  [str],   // fields MISSING from spec (top rec)
        "extraction": {
            "spec_id":            str,
            "spec_text":          str,
            "product":            str,
            "parameters":         {field: value, ...},
            "explicit_standards": [str],
            "specs":              [str]
        },
        "ranking": {
            "spec_id":   str,
            "spec_text": str,
            "recommendations": [
                {
                    "is_code":           str,
                    "title":             str,
                    "semantic_score":    float,   // L2 distance; lower = closer
                    "compliance_status": "compliant"|"partial"|"non-compliant"|"unknown",
                    "passed_fields":     [str],
                    "failed_fields":     [str],
                    "missing_fields":    [str]
                },
                ...  // sorted: compliant > partial > unknown > non-compliant,
                     // then by semantic_score ascending within each tier
            ]
        },
        "rag": {
            "status":   "ok",
            "spec_id":  str,
            "explanations": [
                {
                    "is_code":           str,
                    "title":             str,
                    "semantic_score":    float,
                    "compliance_status": str,
                    "explanation":       str    // Markdown; LLM or template fallback
                },
                ...
            ]
        }
    }

    Response — Ambiguous path (HTTP 200)
    -------------------------------------
    Returned when semantic search cannot identify a clear winner
    (top L2 score > 1.0 OR gap between #1 and #2 < 0.15).

    {
        "status":     "needs_clarification",
        "filename":   str,
        "question":   str,   // clarifying question generated by Groq (or fallback)
        "candidates": [
            {"is_code": str, "title": str, "description": str, "score": float},
            ...
        ]
    }

    Error responses
    ---------------
    400  No file uploaded, or filename is empty
    400  Uploaded file is not a PDF (.pdf extension required)
    422  PDF contains no extractable text (scanned/image-only PDF)
    500  Unexpected internal error (detail message included)

    Notes
    -----
    - ML models (FAISS index + SentenceTransformer) are loaded once at server startup
      as module-level singletons in semantic_search/search.py — not per-request.
    - All LLM calls carry an explicit timeout=10s to prevent hung requests.
    - CORS: allow_origins=["*"], allow_credentials=False (browser-safe wildcard config).
    """

    # Check that a file was uploaded
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file was uploaded."
        )

    # Check PDF extension
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF file."
        )

    temp_path = None

    try:
        # --------------------------------------------------
        # 1. Save uploaded PDF temporarily
        # --------------------------------------------------

        file_content = await file.read()

        # Reject empty files immediately — avoid writing a 0-byte temp file
        if not file_content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty. Please upload a valid PDF."
            )

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf"
        ) as temp_file:
            temp_file.write(file_content)
            temp_path = temp_file.name

        # --------------------------------------------------
        # 2. NLP Extraction
        # --------------------------------------------------

        extracted = extract_from_pdf(temp_path)

        # Override the spec_id with the original uploaded filename stem
        # (extract_from_pdf derives spec_id from the temp file path, which
        # produces a meaningless OS temp name like "tmp5rxsuzic")
        original_stem = Path(file.filename).stem
        extracted["spec_id"] = original_stem

        spec_id         = original_stem
        spec_text       = extracted.get("spec_text", "")
        spec_parameters = extracted.get("parameters", {})

        # Make sure extraction produced text
        if not spec_text:
            # Detect scanned/image-only PDF and give a specific error message
            page_count_hint = ""
            try:
                import pymupdf
                doc = pymupdf.open(temp_path)
                total_pages = len(doc)
                text_pages  = sum(1 for p in doc if p.get_text().strip())
                doc.close()
                if text_pages == 0:
                    page_count_hint = (
                        f" The uploaded file appears to be a scanned or image-only PDF "
                        f"({total_pages} page(s), 0 with selectable text). "
                        f"Please upload a PDF with a text layer, or use OCR software first."
                    )
            except Exception:
                pass
            raise HTTPException(
                status_code=422,
                detail=f"Could not extract a specification from the PDF.{page_count_hint}",
            )

        # --------------------------------------------------
        # 3. Semantic Search
        # --------------------------------------------------

        semantic_results = semantic_search(spec_text, top_k=5)

        # --------------------------------------------------
        # 4. Ambiguity Detection
        #    If search is not confident, return a clarification request
        #    immediately — no compliance ranking attempted on ambiguous results.
        #
        #    Bypass condition: if the NLP extractor found explicit IS code
        #    citations in the tender document (e.g. "IS 10322"), the user has
        #    already named the standard — the query is unambiguous regardless
        #    of how close the embedding scores are.  Skip the clarification
        #    path in that case and proceed straight to ranking.
        # --------------------------------------------------

        explicit_standards = extracted.get("explicit_standards", [])
        if is_ambiguous(semantic_results) and not explicit_standards:
            question = generate_clarifying_question(spec_text, semantic_results)
            candidates = [
                {
                    "is_code":     r["is_code"],
                    "title":       r["title"],
                    "description": r["description"],
                    "score":       r["l2_score"],
                }
                for r in semantic_results
            ]
            return {
                "status":     "needs_clarification",
                "filename":   file.filename,
                "question":   question,
                "candidates": candidates,
            }

        # --------------------------------------------------
        # 5. Ranking + Compliance
        # --------------------------------------------------

        ranked_results = rank_recommendations(
            spec_id=spec_id,
            spec_text=spec_text,
            spec_parameters=spec_parameters,
            semantic_results=semantic_results,
        )

        # --------------------------------------------------
        # 6. Mandatory / Advisory field summary  (top-level)
        # --------------------------------------------------

        mandatory_summary = _compute_mandatory_fields(
            ranked_results.get("recommendations", [])
        )

        # --------------------------------------------------
        # 7. RAG Explanation
        # --------------------------------------------------

        rag_response = generate_rag_response(ranked_results)

        # --------------------------------------------------
        # 8. Return final response
        # --------------------------------------------------

        return {
            "status":                  "ok",
            "filename":                file.filename,
            # Top-level mandatory compliance verdict (Step 3 requirement)
            "is_mandatory_compliant":  mandatory_summary["is_mandatory_compliant"],
            "mandatory_failed_fields": mandatory_summary["mandatory_failed_fields"],
            "advisory_failed_fields":  mandatory_summary["advisory_failed_fields"],
            # Full pipeline outputs
            "extraction":              extracted,
            "ranking":                 ranked_results,
            "rag":                     rag_response,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing tender: {str(e)}"
        )

    finally:
        # --------------------------------------------------
        # Delete temporary PDF
        # On Windows, PyMuPDF may briefly hold the file handle
        # open after returning. Retry once after a short sleep,
        # then silently give up — the OS will clean temp files.
        # --------------------------------------------------
        if temp_path:
            import time
            for attempt in range(3):
                try:
                    Path(temp_path).unlink(missing_ok=True)
                    break
                except (PermissionError, OSError):
                    if attempt < 2:
                        time.sleep(0.2)
                    # Final attempt failed — leave for OS cleanup, don't raise
