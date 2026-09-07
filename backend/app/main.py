from pathlib import Path
import tempfile
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from nlp_extraction.extractor import extract_from_pdf
from semantic_search.search import semantic_search
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
# Process Tender
# --------------------------------------------------

@app.post("/process-tender")
async def process_tender(file: UploadFile = File(...)):
    """
    Upload a tender PDF and process it through:

    1. NLP extraction
    2. Semantic search
    3. Compliance ranking
    4. RAG explanation
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

        spec_id = original_stem
        spec_text = extracted.get("spec_text", "")
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

        semantic_results = semantic_search(
            spec_text,
            top_k=5
        )

        # --------------------------------------------------
        # 4. Ranking + Compliance
        # --------------------------------------------------

        ranked_results = rank_recommendations(
            spec_id=spec_id,
            spec_text=spec_text,
            spec_parameters=spec_parameters,
            semantic_results=semantic_results,
        )

        # --------------------------------------------------
        # 5. RAG Explanation
        # --------------------------------------------------

        rag_response = generate_rag_response(
            ranked_results
        )

        # --------------------------------------------------
        # 6. Return final response
        # --------------------------------------------------

        return {
            "status": "ok",
            "filename": file.filename,
            "extraction": extracted,
            "ranking": ranked_results,
            "rag": rag_response,
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