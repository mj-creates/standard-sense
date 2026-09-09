import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

index = faiss.read_index("semantic_search/is_index.faiss")
with open("semantic_search/is_metadata.json", "r", encoding="utf-8") as f:
    metadata = json.load(f)

model = SentenceTransformer("all-MiniLM-L6-v2")

queries = [
    "High Yield Strength Deformed HYSD bars Grade Fe 500 reinforcement bars",
    "M25 grade concrete mix 28-day characteristic compressive strength 25 MPa",
    "maximum allowable water-cement ratio 0.45 structural concrete",
    "Ordinary Portland Cement OPC 43 Grade fineness setting time chemical composition"
]

results = []
for q in queries:
    embedding = model.encode([q], convert_to_numpy=True).astype(np.float32)
    D, I = index.search(embedding, 3) # Top 3 per query to get total around 10
    for i, idx in enumerate(I[0]):
        if idx != -1:
            meta = metadata[str(idx)]
            results.append({
                "query": q,
                "is_code": meta['is_code'],
                "title": meta['title'],
                "score": float(D[0][i])
            })

with open("search_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
