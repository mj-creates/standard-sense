# Run locally with:
#   uvicorn semantic_search.api:app --reload --port 8000

from fastapi import FastAPI
from pydantic import BaseModel, Field

# Importing semantic_search triggers module-level loading of the FAISS index,
# metadata, and SentenceTransformer model exactly once at startup.
from semantic_search.search import semantic_search

app = FastAPI(
    title="Standard-Sense Semantic Search",
    description="Search Indian Standards (IS codes) by natural-language procurement spec.",
    version="0.1.0",
)


# ── Request / Response schemas ────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., description="Natural-language procurement specification text")
    top_k: int = Field(5, ge=1, le=30, description="Number of results to return (default 5)")


class SearchResult(BaseModel):
    is_code: str
    title: str
    description: str
    score: float = Field(..., description="L2 distance — lower means closer match")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", summary="Health check")
def health():
    """Returns OK so teammates can verify the service is up."""
    return {"status": "ok"}


@app.post("/semantic-search", response_model=list[SearchResult], summary="Semantic search over IS standards")
def search(request: SearchRequest):
    """
    Accepts a procurement spec query and returns the top_k most semantically
    similar Indian Standards with their IS code, title, description, and L2 score.
    """
    raw = semantic_search(request.query, top_k=request.top_k)
    return [
        SearchResult(
            is_code=r["is_code"],
            title=r["title"],
            description=r["description"],
            score=r["l2_score"],
        )
        for r in raw
    ]
