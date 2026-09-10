import os
import json
import sqlite3
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from groq import Groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class ComplianceEngine:
    def __init__(self):
        print("Initializing Compliance Engine...")
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

        # Load FAISS index
        faiss_path = "semantic_search/is_index.faiss"
        if not os.path.exists(faiss_path):
            raise FileNotFoundError(f"Uninitialized FAISS index. Missing file: {faiss_path}")
        self.index = faiss.read_index(faiss_path)

        # Load FAISS metadata
        self.metadata = {}
        meta_path = "semantic_search/is_metadata.json"
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
        else:
            raise FileNotFoundError(f"Metadata file missing: {meta_path}")

        # Initialize Groq client
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set.")
        self.groq_client = Groq(api_key=api_key)

        self.db_path = "sih_standards.db"

    def get_metadata_from_sqlite(self, is_code):
        """Extract matching standard metadata from SQLite"""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Master Database missing at {self.db_path}")

        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT title FROM standards WHERE is_code=?", (is_code,))
            row = c.fetchone()
            conn.close()

            if row is None:
                raise ValueError(f"Missing database row for standard code: {is_code}")

            return {"is_code": is_code, "title": row[0]}
        except sqlite3.OperationalError as e:
            raise RuntimeError(f"Database operational error: {e}")

    def search_top_standards(self, query_text, k=10, department=None, department_override=None, explicit_codes=None):
        """Encode tender clause, query FAISS, filter by department, apply explicit code boost, and extract metadata."""
        if department_override:
            department = department_override

        if explicit_codes is None:
            explicit_codes = set()

        print(f"Searching top {k} standards for clause: '{query_text[:50]}...'")
        embedding = self.model.encode([query_text], convert_to_numpy=True).astype(np.float32)

        search_k = k * 5 if department else k
        D, I = self.index.search(embedding, search_k)

        results = []
        for i, idx in enumerate(I[0]):
            if idx == -1:
                continue
            str_idx = str(idx)
            is_code = "Unknown"
            title = "Unknown"
            entry_department = None

            if str_idx in self.metadata:
                is_code = self.metadata[str_idx].get("is_code", is_code)
                title = self.metadata[str_idx].get("title", title)
                entry_department = self.metadata[str_idx].get("department")

            if department and entry_department and department.lower() not in entry_department.lower():
                continue

            db_meta = self.get_metadata_from_sqlite(is_code)
            if db_meta:
                title = db_meta.get("title", title)

            score = float(D[0][i])
            if is_code in explicit_codes:
                score = -1.0

            results.append({
                "is_code": is_code,
                "title": title,
                "score": score,
            })

            if len(results) >= k:
                break

        results.sort(key=lambda r: r["score"])
        return results

    def benchmark_with_groq(self, standard_code, title, tender_clause):
        """Utilize Groq API to extract structural threshold metrics."""
        print(f"Extracting benchmarks with Groq for {standard_code}...")
        prompt = f"""
You are an expert engineering compliance AI.
Extract structural threshold metrics from the provided tender clause and map them against the IS standard.
Standard: {standard_code} - {title}
Tender Clause: {tender_clause}

Output valid JSON strictly in this format:
{{
  "field_name": "Name of the technical parameter",
  "field_type": "Mandatory or Advisory",
  "benchmark_threshold": "Numeric value and unit or descriptive threshold"
}}
"""
        try:
            response = self.groq_client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": "You are a precise technical extractor that only outputs valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            return {"error": str(e)}

if __name__ == "__main__":
    engine = ComplianceEngine()

    sample_clause = "All structural elements shall be constructed using a minimum of M25 grade concrete mix. The 28-day characteristic compressive strength must achieve at least 25 MPa."

    print("\n--- Running Vector Search ---")
    top_standards = engine.search_top_standards(sample_clause, k=3)
    for idx, std in enumerate(top_standards):
        try:
            print(f"{idx+1}. {std['is_code']} : {std['title']} (Score: {std['score']:.4f})")
        except UnicodeEncodeError:
            title_clean = std['title'].encode('ascii', 'ignore').decode('ascii')
            print(f"{idx+1}. {std['is_code']} : {title_clean} (Score: {std['score']:.4f})")

    if top_standards:
        top_match = top_standards[0]
        print("\n--- Running LLM Parameterization ---")
        metrics = engine.benchmark_with_groq(top_match["is_code"], top_match["title"], sample_clause)
        print("Extracted Metrics:")
        print(json.dumps(metrics, indent=2))