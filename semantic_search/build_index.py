"""
build_index.py
Loads mock IS standards, encodes them with SentenceTransformer,
builds a FAISS IndexFlatL2 index, and saves the index + metadata mapping.
"""

import json
import pathlib
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# ── Paths ────────────────────────────────────────────────────────────────────
HERE = pathlib.Path(__file__).parent
DATA_FILE   = HERE / "mock_is_standards.json"
INDEX_FILE  = HERE / "is_index.faiss"
META_FILE   = HERE / "is_metadata.json"

MODEL_NAME = "all-MiniLM-L6-v2"

# ── Load data ─────────────────────────────────────────────────────────────────
print("Loading IS standards data...")
with open(DATA_FILE, "r", encoding="utf-8") as f:
    standards = json.load(f)

# Concatenate title + description into one searchable string per entry
texts = [
    f"{entry['title']}. {entry['description']}"
    for entry in standards
]

print(f"  {len(texts)} entries loaded.")

# ── Encode ────────────────────────────────────────────────────────────────────
print(f"Loading SentenceTransformer model '{MODEL_NAME}'...")
model = SentenceTransformer(MODEL_NAME)

print("Encoding entries...")
embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
embeddings = embeddings.astype(np.float32)   # FAISS expects float32

print(f"  Embedding shape: {embeddings.shape}")

# ── Build FAISS index ─────────────────────────────────────────────────────────
dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(embeddings)

print(f"  FAISS index built — {index.ntotal} vectors, dimension {dimension}.")

# ── Save index ────────────────────────────────────────────────────────────────
faiss.write_index(index, str(INDEX_FILE))
print(f"  Index saved to: {INDEX_FILE}")

# ── Save metadata mapping (index position -> standard info) ───────────────────
metadata = {
    str(i): {
        "is_code":     entry["is_code"],
        "title":       entry["title"],
        "description": entry["description"],
    }
    for i, entry in enumerate(standards)
}

with open(META_FILE, "w", encoding="utf-8") as f:
    json.dump(metadata, f, indent=2, ensure_ascii=False)

print(f"  Metadata saved to: {META_FILE}")

print(f"\nDone. {index.ntotal} IS standards indexed successfully.")
