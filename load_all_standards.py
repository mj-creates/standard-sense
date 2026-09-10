"""
load_all_standards.py
One-shot ingestion: reads every department .xlsx in standards_data/,
loads them into sih_standards.db, rewrites mock_is_standards.json
(now the REAL full dataset, not mock), and rebuilds the FAISS index.

Run this once from the repo root:
    python load_all_standards.py

Safe to re-run any time you add/update an xlsx file — it fully
replaces the standards table and rebuilds the index from scratch,
so there's no more manual per-code insertion needed.
"""

import glob
import json
import os
import re
import sqlite3

import numpy as np
import openpyxl
import faiss
from sentence_transformers import SentenceTransformer

DATA_DIR = "standards_data"
DB_PATH = "sih_standards.db"
MOCK_JSON = "semantic_search/mock_is_standards.json"
INDEX_FILE = "semantic_search/is_index.faiss"
META_FILE = "semantic_search/is_metadata.json"
MODEL_NAME = "all-MiniLM-L6-v2"


def department_from_filename(path):
    name = os.path.basename(path).replace("_Department.xlsx", "")
    name = name.replace("&", " & ")
    return name.strip()


def load_all_rows():
    """Read every xlsx, return list of dicts: is_code, title, description, department."""
    entries = []
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.xlsx")))
    print(f"Found {len(files)} department files.")

    for f in files:
        dept = department_from_filename(f)
        wb = openpyxl.load_workbook(f, read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))

        count = 0
        for r in rows[2:]:  # skip title row + header row
            is_code, date_pub, title, std_type, equivalence = r[1], r[2], r[3], r[4], r[5]
            if not is_code or not title:
                continue
            description = f"{std_type or ''}. Degree of Equivalence: {equivalence or ''}".strip()
            entries.append({
                "is_code": str(is_code).strip(),
                "title": str(title).strip(),
                "description": description,
                "department": dept,
            })
            count += 1
        print(f"  {dept}: {count} standards")

    print(f"Total: {len(entries)} standards loaded from Excel.")
    return entries


def write_sqlite(entries):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS standards (
            is_code TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            department TEXT
        )
    """)
    # Add department column if the table pre-existed without it
    c.execute("PRAGMA table_info(standards)")
    cols = [row[1] for row in c.fetchall()]
    if "department" not in cols:
        c.execute("ALTER TABLE standards ADD COLUMN department TEXT")

    c.execute("DELETE FROM standards")
    c.executemany(
        "INSERT OR REPLACE INTO standards (is_code, title, description, department) VALUES (?, ?, ?, ?)",
        [(e["is_code"], e["title"], e["description"], e["department"]) for e in entries]
    )
    conn.commit()
    conn.close()
    print(f"SQLite updated: {len(entries)} rows in '{DB_PATH}'.")


def rebuild_faiss(entries):
    print(f"Loading SentenceTransformer model '{MODEL_NAME}'...")
    model = SentenceTransformer(MODEL_NAME)

    texts = [f"{e['title']}. {e['description']}" for e in entries]
    print(f"Encoding {len(texts)} entries (this may take a few minutes)...")
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True).astype(np.float32)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)
    faiss.write_index(index, INDEX_FILE)
    print(f"FAISS index rebuilt: {index.ntotal} vectors -> '{INDEX_FILE}'.")

    metadata = {
        str(i): {
            "is_code": e["is_code"],
            "title": e["title"],
            "description": e["description"],
            "department": e["department"],
        }
        for i, e in enumerate(entries)
    }
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"Metadata saved -> '{META_FILE}'.")

    # Overwrite mock_is_standards.json with the real full dataset so
    # anything that still reads from it (e.g. build_index.py) stays in sync.
    with open(MOCK_JSON, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    print(f"Full dataset written -> '{MOCK_JSON}' ({len(entries)} entries).")


if __name__ == "__main__":
    entries = load_all_rows()
    write_sqlite(entries)
    rebuild_faiss(entries)
    print("\nDone. All IS codes are now loaded into SQLite and indexed in FAISS.")
