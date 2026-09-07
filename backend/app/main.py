from pathlib import Path
import tempfile

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
    allow_credentials=True,
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

        spec_id = extracted.get("spec_id", "")
        spec_text = extracted.get("spec_text", "")
        spec_parameters = extracted.get("parameters", {})

        # Make sure extraction produced text
        if not spec_text:
            raise HTTPException(
                status_code=422,
                detail="Could not extract a specification from the PDF."
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
        # --------------------------------------------------

        if temp_path:
            Path(temp_path).unlink(missing_ok=True)