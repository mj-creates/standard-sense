import sys, json, re, pathlib
sys.path.insert(0, ".")
PASS = "PASS"; FAIL = "BUG"
bugs = []
def check(label, ok, detail=""):
    mark = PASS if ok else FAIL
    print(f"  [{mark}] {label}")
    if not ok:
        bugs.append(f"{label}: {detail}")
        if detail: print(f"         -> {detail}")

print("\n=== LAYER 1: NLP EXTRACTION ===")
from nlp_extraction.extractor import extract_from_pdf
import os
samples = {"electrical":"demo-samples/sample_electrical_cable.pdf","medical":"medical.pdf","plug":"demo-samples/sample_plug_socket.pdf"}
dept_results = {}
for label, path in samples.items():
    if not pathlib.Path(path).exists():
        print(f"  [SKIP] {label}: {path}")
        continue
    print(f"\n  --- {label.upper()}: {path} ---")
    result = extract_from_pdf(str(pathlib.Path(path)))
    dept = result.get("department"); params = result.get("parameters",{}); stds = result.get("explicit_standards",[]); prod = result.get("product",""); spec_text = result.get("spec_text","")
    dept_results[label] = dept
    check(f"[{label}] product extracted", bool(prod), f"product={prod!r}")
    check(f"[{label}] spec_text > 50 chars", len(spec_text)>50, f"len={len(spec_text)}")
    check(f"[{label}] department extracted", dept is not None, f"department={dept!r}")
    check(f"[{label}] parameters non-empty", len(params)>0, f"keys={list(params.keys())}")
    print(f"         product={prod!r}  dept={dept!r}  params={list(params.keys())}  stds={stds}")

print("\n=== LAYER 2: DEPARTMENT LABEL MAPPING ===")
import sqlite3
conn = sqlite3.connect("sih_standards.db"); c = conn.cursor()
c.execute("SELECT DISTINCT department FROM standards"); db_depts={row[0] for row in c.fetchall()}; conn.close()
print(f"  DB departments: {sorted(db_depts)}")
from semantic_search.search import _DEPT_LABEL_TO_DB
for label, dept in dept_results.items():
    if dept is None: continue
    mapped = _DEPT_LABEL_TO_DB.get(dept)
    check(f"[{label}] '{dept}' maps to valid DB dept", mapped is not None and mapped in db_depts, f"mapped={mapped!r}")

print("\n=== LAYER 3: SEMANTIC SEARCH ===")
from semantic_search.search import semantic_search
test_queries = [
    ("PVC insulated copper cable 1100V power distribution","ELECTRICAL"),
    ("ECG patient monitor SpO2 hospital medical device","MEDICAL_EQUIPMENT"),
    ("cement mortar brick masonry construction civil","CIVIL"),
]
for query, dept in test_queries:
    results = semantic_search(query, top_k=5, department=dept)
    check(f"[{dept}] returns >0 results", len(results)>0, f"got {len(results)}")
    if results:
        top = results[0]
        check(f"[{dept}] top L2 < 1.5", top["l2_score"]<1.5, f"l2={top['l2_score']}")
        print(f"    Top: {top['is_code']} | L2={top['l2_score']} | {top['title'][:55]}")

print("\n=== LAYER 4: COMPLIANCE CHECKER ===")
from compliance_ranking.compliance_checker import check_compliance, _REQUIREMENTS
mapped_code = list(_REQUIREMENTS.keys())[0] if _REQUIREMENTS else None
if mapped_code:
    comp = check_compliance({}, mapped_code)
    check("mapped standard returns status", comp.get("status") in {"compliant","partial","non-compliant","unknown"}, str(comp.get("status")))
unmapped = "IS/IEC 80601 (Part 2/Sec 49):2018"
comp2 = check_compliance({}, unmapped)
check("unmapped -> status=unknown", comp2.get("status")=="unknown", str(comp2.get("status")))
check("unmapped -> no passed_fields", comp2.get("passed_fields")==[], str(comp2.get("passed_fields")))

print("\n=== LAYER 5: RANKING ENGINE ===")
from compliance_ranking.ranking_engine import rank_recommendations
sem = semantic_search("PVC cable 1100V power distribution", top_k=8, department="ELECTRICAL")
ranked = rank_recommendations("test","PVC insulated cable 1100V",{"voltage":"1100V"},sem)
recs=ranked.get("recommendations",[]); also=ranked.get("also_considered",[])
check("recommendations count == 5", len(recs)==5, f"got {len(recs)}")
check("also_considered count == 3", len(also)==3, f"got {len(also)}")
if recs:
    check("rec[0] has semantic_score", "semantic_score" in recs[0], str(list(recs[0].keys())))
    check("rec[0] has compliance_status", "compliance_status" in recs[0], str(list(recs[0].keys())))

print("\n=== LAYER 6: RAG ENGINE ===")
from rag_feedback.rag.rag_engine import generate_explanation, generate_rag_response
if recs:
    spec_text_s = "PVC insulated copper cable 1100V industrial power distribution"
    exp_text = generate_explanation(spec_text_s, recs[0])
    check("explanation non-empty", bool(exp_text.strip()), "empty")
    raw_bold = bool(re.search(r"\*\*[^*]+\*\*", exp_text))
    check("explanation has no raw **bold** markdown", not raw_bold, f"raw md found: {re.findall(r'\\*\\*[^*]+\\*\\*', exp_text)[:2]}")
    print(f"  Sample (first 300 chars): {exp_text[:300]!r}")

    rag_out = generate_rag_response(ranked)
    check("rag status=ok", rag_out.get("status")=="ok", str(rag_out.get("status")))
    check("explanations count == 5", len(rag_out.get("explanations",[]))==5, f"got {len(rag_out.get('explanations',[]))}")
    for i,e in enumerate(rag_out.get("explanations",[])):
        for f in ["is_code","title","semantic_score","compliance_status","explanation"]:
            check(f"exp[{i}].{f} present", f in e)

print("\n=== LAYER 7: FULL PIPELINE (electrical sample) ===")
elec = "demo-samples/sample_electrical_cable.pdf"
if pathlib.Path(elec).exists():
    ex = extract_from_pdf(elec)
    s = semantic_search(ex.get("spec_text",""), top_k=8, department=ex.get("department"))
    check("full pipeline semantic non-empty", len(s)>0, f"got {len(s)}")
    r2 = rank_recommendations("elec", ex.get("spec_text",""), ex.get("parameters",{}), s)
    recs2 = r2.get("recommendations",[])
    check("full pipeline recs non-empty", len(recs2)>0, f"got {len(recs2)}")
    rag2 = generate_rag_response(r2)
    check("full pipeline rag ok", rag2.get("status")=="ok", str(rag2.get("status")))

print("\n=== LAYER 8: FRONTEND JS CHECKS ===")
js_src = pathlib.Path("frontend/app.js").read_text(encoding="utf-8")
logout_count = len(re.findall(r"\bfunction handleLogout\b", js_src))
check("handleLogout declared once only", logout_count==1, f"found {logout_count} declarations")
has_call = "_resetUploadState" in js_src
is_def = bool(re.search(r"function _resetUploadState\b", js_src))
check("_resetUploadState defined if called", not has_call or is_def, "_resetUploadState called but never defined")
short_uses_eschtml = bool(re.search(r"_escHtml\(shortExplanation\)", js_src))
check("short preview does NOT use raw _escHtml on markdown text", not short_uses_eschtml,
      "short preview uses _escHtml(shortExplanation) — ** will show as literal asterisks in the 3-line preview")

print("\n=== SUMMARY ===")
if bugs:
    print(f"\n  {len(bugs)} bug(s):")
    for i,b in enumerate(bugs,1): print(f"  {i}. {b}")
else:
    print("  No bugs found.")
