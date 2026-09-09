"""
verify_dev.py
-------------
End-to-end integration harness for the StandardSense dev pipeline.
Runs: NLP Extraction -> Semantic Search -> Compliance Ranking -> RAG Generation
"""

import json
import os
import pathlib
import sys
import traceback

# Ensure project root on path
ROOT = pathlib.Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

# Silence HuggingFace network checks — model already cached
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

PDF_PATH = ROOT / "data" / "sample_tenders" / "sample_tender_01.pdf"

SEP  = "=" * 68
SEP2 = "-" * 68

def banner(step, title):
    print(f"\n{SEP}\n  STEP {step}: {title}\n{SEP}")

def ok(msg):   print(f"  [OK]  {msg}")
def err(msg):  print(f"  [ERR] {msg}")
def info(msg): print(f"  ...   {msg}")

# ── STEP 1: NLP Extraction ────────────────────────────────────────────────────
banner(1, "NLP EXTRACTION")

try:
    from nlp_extraction.extractor import extract_from_pdf
    ok("extract_from_pdf imported")
except ImportError as e:
    err(f"Import failed: {e}")
    err("Is pymupdf installed? Run: pip install pymupdf")
    sys.exit(1)

try:
    info(f"Running on: {PDF_PATH}")
    raw_result = extract_from_pdf(str(PDF_PATH))
    # extractor returns a plain dict — handle both dict and dataclass
    if hasattr(raw_result, "to_dict"):
        extraction = raw_result.to_dict()
    elif isinstance(raw_result, dict):
        extraction = raw_result
    else:
        extraction = dict(raw_result)
    ok(f"Extraction complete")
    info(f"spec_id    : {extraction.get('spec_id')}")
    info(f"product    : {extraction.get('product')}")
    info(f"spec_text  : {extraction.get('spec_text', '')[:100]}...")
    info(f"parameters : {extraction.get('parameters')}")
    info(f"standards  : {extraction.get('explicit_standards')}")
except Exception as e:
    err(f"NLP Extraction failed: {e}")
    traceback.print_exc()
    sys.exit(1)

spec_id     = extraction["spec_id"]
spec_text   = extraction["spec_text"]
parameters  = extraction.get("parameters", {})

# ── STEP 2: Semantic Search ───────────────────────────────────────────────────
banner(2, "SEMANTIC SEARCH")

try:
    from semantic_search.search import semantic_search, is_ambiguous
    ok("semantic_search imported (FAISS index + SentenceTransformer loaded)")
except ImportError as e:
    err(f"Import failed: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    info(f"Querying with spec_text (top_k=5)...")
    search_results = semantic_search(spec_text, top_k=5)
    ambiguous = is_ambiguous(search_results)
    ok(f"Search returned {len(search_results)} results  |  is_ambiguous={ambiguous}")
    print(f"\n  {'Rank':<5} {'IS Code':<12} {'Score':<10} Title")
    print(f"  {'-'*60}")
    for r in search_results:
        print(f"  #{r['rank']:<4} {r['is_code']:<12} {r['l2_score']:<10.4f} {r['title'][:50]}")
except Exception as e:
    err(f"Semantic Search failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# ── STEP 3: Compliance Ranking ────────────────────────────────────────────────
banner(3, "COMPLIANCE RANKING")

try:
    from compliance_ranking.ranking_engine import rank_recommendations
    ok("rank_recommendations imported")
except ImportError as e:
    err(f"Import failed: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    info(f"spec_id={spec_id}  |  {len(parameters)} extracted parameters  |  {len(search_results)} candidates")
    ranked = rank_recommendations(
        spec_id=spec_id,
        spec_text=spec_text,
        spec_parameters=parameters,
        semantic_results=search_results,
    )
    recs = ranked.get("recommendations", [])
    ok(f"Ranking complete — {len(recs)} recommendations")
    print(f"\n  {'#':<4} {'IS Code':<12} {'Compliance':<16} {'Sem.Score':<10} Title")
    print(f"  {'-'*68}")
    for i, r in enumerate(recs, 1):
        print(f"  #{i:<3} {r['is_code']:<12} {r['compliance_status']:<16} {r['semantic_score']:<10.4f} {r['title'][:36]}")
except Exception as e:
    err(f"Compliance Ranking failed: {e}")
    info("Dumping search_results shape for diagnosis:")
    for r in search_results:
        info(str({k: type(v).__name__ for k, v in r.items()}))
    traceback.print_exc()
    sys.exit(1)

# ── STEP 4: RAG Generation ────────────────────────────────────────────────────
banner(4, "RAG GENERATION")

try:
    from rag_feedback.rag.rag_engine import generate_rag_response
    ok("generate_rag_response imported")
except ImportError as e:
    err(f"Import failed: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    info(f"Passing ranked output (spec_id={ranked['spec_id']}, {len(recs)} recs)...")
    rag_output = generate_rag_response(ranked)
    ok(f"RAG generation complete  |  status={rag_output.get('status')}  |  {len(rag_output.get('explanations', []))} explanations")
    for i, exp in enumerate(rag_output.get("explanations", []), 1):
        print(f"\n  [{i}] {exp['is_code']}  compliance={exp['compliance_status']}")
        # Truncate long explanation for readability
        text = exp.get("explanation", "")
        print(f"      {text[:200]}{'...' if len(text) > 200 else ''}")
except Exception as e:
    err(f"RAG Generation failed: {e}")
    info("Dumping ranked output shape for diagnosis:")
    info(json.dumps({k: type(v).__name__ for k, v in ranked.items()}))
    traceback.print_exc()
    sys.exit(1)

# ── FINAL OUTPUT ──────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  FINAL PIPELINE OUTPUT (JSON)")
print(SEP)
print(json.dumps(rag_output, indent=2))

print(f"\n{SEP}")
print("  PIPELINE HEALTH STATUS")
print(SEP)
stages = {
    "NLP Extraction":    extraction.get("spec_text", "") != "",
    "Semantic Search":   len(search_results) > 0,
    "Compliance Ranking": len(recs) > 0,
    "RAG Generation":    rag_output.get("status") == "ok",
}
all_green = all(stages.values())
for stage, passed in stages.items():
    mark = "GREEN" if passed else "RED"
    print(f"  [{mark}]  {stage}")

print()
print(f"  Overall: {'GREEN - dev pipeline is healthy end-to-end' if all_green else 'RED - pipeline has failures'}")
print(SEP)
