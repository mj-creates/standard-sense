"""
search.py
Loads the saved FAISS index and metadata, then provides a semantic_search()
function that maps a natural-language query to the closest IS standards.

Also provides:
  - is_ambiguous()               — detects low-confidence or too-close results
  - generate_clarifying_question() — calls Groq to produce a follow-up question
"""

import json
import os
import pathlib
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from groq import Groq

# ── Paths ────────────────────────────────────────────────────────────────────
HERE       = pathlib.Path(__file__).parent
INDEX_FILE = HERE / "is_index.faiss"
META_FILE  = HERE / "is_metadata.json"

MODEL_NAME = "all-MiniLM-L6-v2"

# ── Load resources (module-level so they're shared across calls) ──────────────
print("Loading FAISS index and metadata...")
_index = faiss.read_index(str(INDEX_FILE))

with open(META_FILE, "r", encoding="utf-8") as f:
    _metadata = json.load(f)

print(f"Loading SentenceTransformer model '{MODEL_NAME}'...")
_model = SentenceTransformer(MODEL_NAME)

print(f"Ready. Index contains {_index.ntotal} IS standards.\n")


# ── Search function ───────────────────────────────────────────────────────────
def semantic_search(query_text: str, top_k: int = 5, department: str = None) -> list[dict]:
    """
    Embed query_text and return the top_k closest IS standards.

    Returns a list of dicts:
        [{"rank": 1, "is_code": ..., "title": ..., "description": ..., "l2_score": ...}, ...]

    Lower l2_score = closer match.
    """
    # Pre-filter: get valid codes from SQLite
    import sqlite3
    import os
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sih_standards.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    if department:
        c.execute("SELECT is_code FROM standards WHERE department=?", (department,))
    else:
        c.execute("SELECT is_code FROM standards")
    valid_codes = {row[0] for row in c.fetchall()}
    conn.close()

    query_vec = _model.encode([query_text], convert_to_numpy=True).astype(np.float32)
    # Execute FAISS search across all to allow exhaustive subset filtering
    distances, indices = _index.search(query_vec, _index.ntotal)

    results = []
    for idx, dist in zip(indices[0], distances[0]):
        meta = _metadata[str(idx)]
        is_code = meta["is_code"]
        if is_code not in valid_codes:
            continue
            
        results.append({
            "is_code":     is_code,
            "title":       meta["title"],
            "description": meta["description"],
            "l2_score":    round(float(dist), 4),
        })
        
    results.sort(key=lambda x: x["l2_score"])
    top_results = results[:top_k]
    for rank, res in enumerate(top_results, start=1):
        res["rank"] = rank
        
    return top_results


# ── Ambiguity detection ───────────────────────────────────────────────────────

def is_ambiguous(
    results: list[dict],
    low_confidence_threshold: float = 1.0,
    gap_threshold: float = 0.05,
) -> bool:
    """
    Returns True if the search results are too weak or too close to be useful.

    Two independent signals trigger ambiguity:
      1. Low confidence  — top result's l2_score > low_confidence_threshold
         (even the best match is too distant from the query)
      2. Narrow gap      — difference between top and second result's score
         < gap_threshold (no clear winner; multiple standards look equally likely)

    Thresholds (tuned for the 44-standard expanded index):
      low_confidence_threshold=1.0  → scores above 1.0 are treated as weak
      gap_threshold=0.05            → only extremely tight gaps trigger clarification;
                                       LED standards naturally cluster at 0.02–0.06
                                       apart, so 0.05 avoids false positives while
                                       still catching genuinely indistinguishable results
    """
    if len(results) == 0:
        return True

    top_score = results[0]["l2_score"]

    # Signal 1: best match is too far away
    if top_score > low_confidence_threshold:
        return True

    # Signal 2: top two matches are nearly indistinguishable
    if len(results) >= 2:
        gap = results[1]["l2_score"] - top_score
        if gap < gap_threshold:
            return True

    return False


# ── Clarifying question generation ───────────────────────────────────────────

_GROQ_MODEL = "groq/compound-mini"
_FALLBACK_QUESTION = (
    "Could you provide more detail about the material, application, or specific use case?"
)


def generate_clarifying_question(query_text: str, results: list[dict]) -> str:
    """
    Calls the Groq API to generate ONE short clarifying question that would
    help distinguish between the ambiguous top candidate IS standards.

    Requires GROQ_API_KEY to be set as an environment variable.
    Falls back to a generic question on any error.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        # Caller is responsible for checking this upstream; provide fallback here
        return _FALLBACK_QUESTION

    # Build a concise candidate summary (top 3–5 results)
    candidates = results[:5]
    candidate_lines = "\n".join(
        f"- {r['is_code']}: {r['title']} — {r['description'][:120]}..."
        for r in candidates
    )

    prompt = (
        f"A user submitted the following procurement specification query:\n"
        f"\"{query_text}\"\n\n"
        f"The top matching Indian Standards are:\n{candidate_lines}\n\n"
        f"These results are ambiguous — it's unclear which standard the user needs. "
        f"Generate exactly ONE short, specific clarifying question (one sentence, no preamble, "
        f"no numbering, no quotation marks) that would help narrow down which standard applies. "
        f"Focus on the key differentiator between the candidates above."
    )

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=80,
            timeout=10,   # hard cap — clarifying question must not stall the pipeline
        )
        question = response.choices[0].message.content.strip()
        # Strip any leading/trailing quotes or numbering the model might add
        question = question.strip('"\'').lstrip("1. ").strip()
        return question
    except Exception:
        return _FALLBACK_QUESTION


def _print_results(query: str, results: list[dict]) -> None:
    print(f"Query: \"{query}\"")
    print("-" * 72)
    for r in results:
        print(f"  #{r['rank']}  {r['is_code']} | L2: {r['l2_score']}")
        print(f"      {r['title']}")
        # Truncate long descriptions for readability
        desc = r['description']
        if len(desc) > 160:
            desc = desc[:157] + "..."
        print(f"      {desc}")
    print()


# ── Example queries ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    example_queries = [
        "supply of high tensile steel bars for reinforced concrete bridge construction",
        "safety certification for children's plastic toys with battery compartment",
        "PVC insulated copper cables for industrial power distribution up to 1100 volts",
    ]

    print("=" * 72)
    print("SEMANTIC SEARCH — IS STANDARDS")
    print("=" * 72)
    print()

    for query in example_queries:
        results = semantic_search(query, top_k=5)
        _print_results(query, results)
