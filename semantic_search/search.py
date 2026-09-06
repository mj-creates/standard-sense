"""
search.py
Loads the saved FAISS index and metadata, then provides a semantic_search()
function that maps a natural-language query to the closest IS standards.
"""

import json
import pathlib
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

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
def semantic_search(query_text: str, top_k: int = 5) -> list[dict]:
    """
    Embed query_text and return the top_k closest IS standards.

    Returns a list of dicts:
        [{"rank": 1, "is_code": ..., "title": ..., "description": ..., "l2_score": ...}, ...]

    Lower l2_score = closer match.
    """
    query_vec = _model.encode([query_text], convert_to_numpy=True).astype(np.float32)
    distances, indices = _index.search(query_vec, top_k)

    results = []
    for rank, (idx, dist) in enumerate(zip(indices[0], distances[0]), start=1):
        meta = _metadata[str(idx)]
        results.append({
            "rank":        rank,
            "is_code":     meta["is_code"],
            "title":       meta["title"],
            "description": meta["description"],
            "l2_score":    round(float(dist), 4),
        })
    return results


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
