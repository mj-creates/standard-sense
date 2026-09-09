"""
run_pipeline.py
---------------
End-to-end StandardSense pipeline CLI.

Chains three modules — NLP extraction, semantic search, compliance ranking —
without requiring a running FastAPI server.

Usage
-----
    python run_pipeline.py --pdf data/sample_tenders/sample_tender_01.pdf
    python run_pipeline.py --pdf <path> --top-k 8
    python run_pipeline.py --pdf <path> --top-k 5 --no-color

Pipeline steps
--------------
  Step A  NLP Extraction   (nlp_extraction.extractor)
          PDF -> structured spec dict
              {spec_id, spec_text, product, parameters, explicit_standards}

  Step B  Semantic Search  (semantic_search.search)
          spec_text -> top-N candidate IS standards ranked by embedding similarity
              [{rank, is_code, title, description, l2_score}, ...]

  Step C  Compliance + Ranking  (compliance_ranking.ranking_engine)
          candidates + parameters -> final ranked recommendations
              {spec_id, spec_text, recommendations: [{is_code, title,
               semantic_score, compliance_status, passed_fields,
               failed_fields, missing_fields}, ...]}
"""

from __future__ import annotations

import sys
import time
import pathlib
import argparse

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

DEFAULT_PDF = ROOT / "data" / "sample_tenders" / "sample_tender_01.pdf"

# ── ANSI colour helpers (disable with --no-color) ────────────────────────────
USE_COLOR = True

class C:
    """ANSI colour codes — all methods no-op when USE_COLOR is False."""
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    DIM    = "\033[2m"
    BLUE   = "\033[94m"

    @classmethod
    def apply(cls, code: str, text: str) -> str:
        if not USE_COLOR:
            return text
        return f"{code}{text}{cls.RESET}"

    @classmethod
    def bold(cls, t: str) -> str:    return cls.apply(cls.BOLD,   t)
    @classmethod
    def green(cls, t: str) -> str:   return cls.apply(cls.GREEN,  t)
    @classmethod
    def yellow(cls, t: str) -> str:  return cls.apply(cls.YELLOW, t)
    @classmethod
    def red(cls, t: str) -> str:     return cls.apply(cls.RED,    t)
    @classmethod
    def cyan(cls, t: str) -> str:    return cls.apply(cls.CYAN,   t)
    @classmethod
    def blue(cls, t: str) -> str:    return cls.apply(cls.BLUE,   t)
    @classmethod
    def dim(cls, t: str) -> str:     return cls.apply(cls.DIM,    t)
    @classmethod
    def white(cls, t: str) -> str:   return cls.apply(cls.WHITE,  t)


def sep(char: str = "─", width: int = 72) -> str:
    return C.dim(char * width)


def header(title: str, width: int = 72) -> str:
    pad = max(0, width - len(title) - 4)
    left  = pad // 2
    right = pad - left
    bar   = C.dim("─" * left) + C.bold(C.cyan(f"  {title}  ")) + C.dim("─" * right)
    return bar


def status_badge(status: str) -> str:
    """Return a coloured compliance status badge."""
    mapping = {
        "compliant":     C.green,
        "partial":       C.yellow,
        "non-compliant": C.red,
        "unknown":       C.dim,
    }
    colour_fn = mapping.get(status, C.white)
    label = status.upper().replace("-", "‑")   # non-breaking hyphen for display
    return colour_fn(f"[{label}]")


# ── Step A: NLP Extraction ────────────────────────────────────────────────────
def step_extract(pdf_path: str) -> dict:
    print(header("STEP A — NLP EXTRACTION"))
    print(f"  {C.dim('PDF:')} {pdf_path}")
    t0 = time.perf_counter()
    from nlp_extraction.extractor import extract_from_pdf   # noqa: PLC0415
    result = extract_from_pdf(pdf_path)
    elapsed = time.perf_counter() - t0

    print(f"  {C.dim('Completed in')} {elapsed:.2f}s\n")
    print(f"  {C.bold('spec_id')}   : {result['spec_id']}")
    print(f"  {C.bold('product')}   : {result['product'] or C.dim('(not detected)')}")

    params = result.get("parameters", {})
    if params:
        print(f"  {C.bold('parameters')}:")
        for k, v in params.items():
            print(f"    {k:<26} {C.cyan(v)}")
    else:
        print(f"  {C.bold('parameters')} : {C.dim('(none extracted)')}")

    stds = result.get("explicit_standards", [])
    if stds:
        print(f"  {C.bold('explicit IS codes')} : {', '.join(stds)}")

    print(f"\n  {C.bold('spec_text')} (for semantic search):")
    # Wrap spec_text at 68 chars for readability
    text = result["spec_text"]
    for i in range(0, len(text), 68):
        print(f"    {C.white(text[i:i+68])}")
    print()
    return result


# ── Step B: Semantic Search ───────────────────────────────────────────────────
def step_search(spec_text: str, top_k: int) -> list[dict]:
    print(header("STEP B — SEMANTIC SEARCH"))
    print(f"  {C.dim('Loading FAISS index + SentenceTransformer model...')}")
    t0 = time.perf_counter()
    from semantic_search.search import semantic_search, is_ambiguous  # noqa: PLC0415
    load_elapsed = time.perf_counter() - t0

    t1 = time.perf_counter()
    results = semantic_search(spec_text, top_k=top_k)
    search_elapsed = time.perf_counter() - t1

    print(f"  {C.dim('Model load:')} {load_elapsed:.1f}s  "
          f"{C.dim('Search:')} {search_elapsed:.3f}s\n")

    ambiguous = is_ambiguous(results)
    if ambiguous:
        print(f"  {C.yellow('⚠  is_ambiguous() = True')} "
              f"{C.dim('(scores are high/close — real API would trigger clarification)')}")
        print(f"  {C.dim('Pipeline continues: passing results directly to ranking engine.')}\n")
    else:
        print(f"  {C.green('✓  is_ambiguous() = False')} — confident results\n")

    print(f"  {'Rank':<6} {'IS Code':<16} {'L2 Score':<12} Title")
    print(f"  {sep('─', 66)}")
    for r in results:
        score_str = f"{r['l2_score']:.4f}"
        print(f"  #{r['rank']:<5} {r['is_code']:<16} {C.cyan(score_str):<21} {r['title'][:42]}")
    print()
    return results


# ── Step C: Compliance + Ranking ──────────────────────────────────────────────
def step_rank(
    spec_id: str,
    spec_text: str,
    parameters: dict,
    search_results: list[dict],
) -> dict:
    print(header("STEP C — COMPLIANCE CHECK & RANKING"))
    t0 = time.perf_counter()
    from compliance_ranking.ranking_engine import rank_recommendations  # noqa: PLC0415
    output = rank_recommendations(
        spec_id=spec_id,
        spec_text=spec_text,
        spec_parameters=parameters,
        semantic_results=search_results,
    )
    elapsed = time.perf_counter() - t0
    print(f"  {C.dim('Completed in')} {elapsed:.3f}s\n")

    # Handle needs_clarification passthrough
    if output.get("status") == "needs_clarification":
        print(f"  {C.yellow('Status: needs_clarification')}")
        print(f"  Question: {output.get('question', '')}")
        return output

    recs = output.get("recommendations", [])
    print(f"  {C.bold(str(len(recs)))} recommendations — ranked by "
          f"compliance tier {C.dim('then')} semantic score\n")
    return output


# ── Output: Final Summary ─────────────────────────────────────────────────────
def print_summary(output: dict) -> None:
    print(header("FINAL RANKED RECOMMENDATIONS"))

    if output.get("status") == "needs_clarification":
        print(f"  {C.yellow('Ambiguous query — no ranking produced.')}")
        print(f"  {C.bold('Clarifying question:')} {output.get('question', '')}")
        return

    recs = output.get("recommendations", [])
    if not recs:
        print(f"  {C.dim('No recommendations returned.')}")
        return

    # Compliance distribution summary
    from collections import Counter  # noqa: PLC0415
    dist = Counter(r["compliance_status"] for r in recs)
    dist_parts = []
    for status, colour_fn in [
        ("compliant",     C.green),
        ("partial",       C.yellow),
        ("non-compliant", C.red),
        ("unknown",       C.dim),
    ]:
        if dist.get(status, 0):
            dist_parts.append(colour_fn(f"{dist[status]} {status}"))
    print(f"  Distribution: {' · '.join(dist_parts)}\n")

    for i, rec in enumerate(recs, start=1):
        badge      = status_badge(rec["compliance_status"])
        score_str  = f"{rec['semantic_score']:.4f}"
        is_code    = C.bold(rec["is_code"])
        title_clip = rec["title"][:55] + ("…" if len(rec["title"]) > 55 else "")

        print(f"  {C.bold(f'#{i}'):>6}  {is_code:<30}  {badge:<25}  "
              f"{C.dim('L2:')} {C.cyan(score_str)}")
        print(f"         {C.dim(title_clip)}")

        # Field breakdown — only show non-empty lists
        parts = []
        if rec["passed_fields"]:
            parts.append(C.green(f"passed: {', '.join(rec['passed_fields'])}"))
        if rec["failed_fields"]:
            parts.append(C.red(f"failed: {', '.join(rec['failed_fields'])}"))
        if rec["missing_fields"]:
            parts.append(C.yellow(f"missing: {', '.join(rec['missing_fields'])}"))
        if parts:
            print(f"         {C.dim('Fields →')} {' | '.join(parts)}")
        print()

    # Highlight the top recommendation clearly
    top = recs[0]
    print(sep("═"))
    print(f"  {C.bold('TOP RECOMMENDATION')}")
    print(f"  {C.bold(top['is_code'])}  —  {top['title']}")
    print(f"  Compliance : {status_badge(top['compliance_status'])}")
    print(f"  Sem. score : {top['semantic_score']:.4f}  "
          f"{C.dim('(L2 distance — lower = more semantically similar)')}")
    if top["passed_fields"]:
        print(f"  Passed     : {C.green(', '.join(top['passed_fields']))}")
    if top["failed_fields"]:
        print(f"  Failed     : {C.red(', '.join(top['failed_fields']))}")
    if top["missing_fields"]:
        print(f"  Missing    : {C.yellow(', '.join(top['missing_fields']))}")
    print(sep("═"))
    print()


# ── Argument parsing ──────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_pipeline.py",
        description="StandardSense end-to-end pipeline: PDF → extraction → "
                    "semantic search → compliance ranking.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pdf",
        default=str(DEFAULT_PDF),
        help=f"Path to the tender PDF file. Default: {DEFAULT_PDF}",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=7,
        dest="top_k",
        help="Number of IS standards to retrieve from semantic search (default: 7).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        dest="no_color",
        help="Disable ANSI colour output (useful for piping or log files).",
    )
    return parser.parse_args()


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    args = parse_args()

    global USE_COLOR
    USE_COLOR = not args.no_color

    # Force UTF-8 stdout to survive degree symbols, em-dashes etc on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pdf_path = args.pdf
    top_k    = args.top_k

    print()
    print(sep("═"))
    print(C.bold(C.cyan(
        "  StandardSense — IS Standards Compliance Pipeline"
    )))
    print(sep("═"))
    print(f"  PDF    : {pdf_path}")
    print(f"  Top-K  : {top_k}")
    print(sep("═"))
    print()

    total_t0 = time.perf_counter()

    # ── A: Extract ────────────────────────────────────────────────────────────
    try:
        extraction = step_extract(pdf_path)
    except FileNotFoundError as exc:
        print(C.red(f"  ERROR: {exc}"))
        print(C.dim("  Hint: use --pdf <path> to specify the PDF location."))
        sys.exit(1)
    except Exception as exc:
        print(C.red(f"  ERROR during extraction: {exc}"))
        raise

    spec_id    = extraction["spec_id"]
    spec_text  = extraction["spec_text"]
    parameters = extraction.get("parameters", {})

    if not spec_text.strip():
        print(C.red("  ERROR: Extraction produced no spec_text — cannot search."))
        sys.exit(1)

    # ── B: Search ─────────────────────────────────────────────────────────────
    try:
        search_results = step_search(spec_text, top_k=top_k)
    except Exception as exc:
        print(C.red(f"  ERROR during semantic search: {exc}"))
        raise

    # ── C: Rank ───────────────────────────────────────────────────────────────
    try:
        output = step_rank(spec_id, spec_text, parameters, search_results)
    except Exception as exc:
        print(C.red(f"  ERROR during compliance ranking: {exc}"))
        raise

    # ── Summary ───────────────────────────────────────────────────────────────
    print_summary(output)

    total_elapsed = time.perf_counter() - total_t0
    print(C.dim(f"  Total pipeline time: {total_elapsed:.1f}s"))
    print()


if __name__ == "__main__":
    main()
