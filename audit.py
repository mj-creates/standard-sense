import os
import glob
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer

# 1. Inspect Workspace for SQLite / Vector indices
print("--- 1. Workspace Inspection ---")
db_files = glob.glob("**/*.db", recursive=True)
sqlite_files = glob.glob("**/*.sqlite", recursive=True)
faiss_files = glob.glob("**/*.faiss", recursive=True)
pkl_files = glob.glob("**/*.pkl", recursive=True)

print("DB Files:", db_files + sqlite_files)
print("FAISS/Index Files:", faiss_files + pkl_files)

# 2. Embedding Model
print("\n--- 2. Embedding Model Inspection ---")
model_name = "all-MiniLM-L6-v2"
device = "GPU" if torch.cuda.is_available() else "CPU"
try:
    model = SentenceTransformer(model_name)
    dim = model.get_sentence_embedding_dimension()
    print(f"Model: {model_name}")
    print(f"Dimension: {dim}")
    print(f"Device: {device}")
except Exception as e:
    print(f"Error loading model: {e}")

# 3. Standards Data Verification
print("\n--- 3. Standards Data Verification ---")
data_dir = "standards_data"
files = glob.glob(os.path.join(data_dir, "*.xlsx"))
total_rows = 0
for f in files:
    try:
        df = pd.read_excel(f)
        rows = len(df)
        total_rows += rows
        cols = list(df.columns)
        print(f"File: {os.path.basename(f)} | Rows: {rows} | Schema: {cols}")
    except Exception as e:
        print(f"File: {os.path.basename(f)} | Error: {e}")

print(f"Total Rows across 7 departments: {total_rows}")

# 4. LLM API Key Check
print("\n--- 4. LLM Integration Parameters ---")
from dotenv import load_dotenv
load_dotenv()
groq_key = os.environ.get("GROQ_API_KEY")
if groq_key:
    print("GROQ_API_KEY: Detected")
else:
    print("GROQ_API_KEY: Not Found")
