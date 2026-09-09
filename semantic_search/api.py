# Run locally with:
#   uvicorn semantic_search.api:app --reload --port 8000

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Importing these triggers module-level loading of the FAISS index,
# metadata, and SentenceTransformer model exactly once at startup.
from semantic_search.search import (
    semantic_search,
    is_ambiguous,
    generate_clarifying_question,
)

app = FastAPI(
    title="Standard-Sense Semantic Search",
    description="Search Indian Standards (IS codes) by natural-language procurement spec.",
    version="0.3.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# TODO: Restrict allow_origins to the actual frontend origin once integration
#       begins (e.g. ["http://localhost:3000", "https://standard-sense.app"]).
#       Using ["*"] only while frontend origin is unknown.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response schemas ────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(default="", description="Natural-language procurement specification text")
    top_k: int = Field(5, description="Number of results to return (default 5)")


class SearchResult(BaseModel):
    is_code: str
    title: str
    description: str
    score: float = Field(..., description="L2 distance — lower means closer match")


def _to_result(r: dict) -> dict:
    """Convert a raw search result dict to the API response shape."""
    return {
        "is_code":     r["is_code"],
        "title":       r["title"],
        "description": r["description"],
        "score":       r["l2_score"],
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", summary="Health check")
def health():
    """Returns OK so teammates can verify the service is up."""
    return {"status": "ok"}


@app.post(
    "/semantic-search",
    summary="Semantic search over IS standards",
    response_class=JSONResponse,
)
def search(request: SearchRequest):
    """
    Accepts a procurement spec query and returns either:

    Confident match:
        {"status": "ok", "results": [...]}

    Ambiguous match (top score too weak, or top results too close together):
        {"status": "needs_clarification", "question": "...", "candidates": [...]}

    Validation errors return HTTP 400 with {"detail": "<message>"}.
    """
    # ── Input validation ──────────────────────────────────────────────────────
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query text is required.")

    if request.top_k < 1:
        raise HTTPException(status_code=400, detail="top_k must be a positive integer.")

    # ── Search ────────────────────────────────────────────────────────────────
    raw = semantic_search(request.query.strip(), top_k=request.top_k)

    if is_ambiguous(raw):
        question = generate_clarifying_question(request.query.strip(), raw)
        return {
            "status":     "needs_clarification",
            "question":   question,
            "candidates": [_to_result(r) for r in raw],
        }

    return {
        "status":  "ok",
        "results": [_to_result(r) for r in raw],
    }
