"""T7-style regression: run the pipeline on several fixed queries (sequential, slow)."""
from __future__ import annotations

import os
import sys

# Windows / CPU: set before importing torch-backed modules
for _k, _v in (
    ("OMP_NUM_THREADS", "1"),
    ("MKL_NUM_THREADS", "1"),
    ("TOKENIZERS_PARALLELISM", "false"),
):
    os.environ.setdefault(_k, _v)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


QUERIES = [
    "What is LangGraph?",
    "What is LanceDB?",
    "AI regulation 2025",
]


def main() -> int:
    from agents.graph import run_pipeline

    for q in QUERIES:
        print(f"\n=== Query: {q!r} ===", flush=True)
        r = run_pipeline(q)
        wc = r.get("word_count", 0)
        rep = (r.get("report") or "").strip()
        ok = bool(rep) and wc > 0
        print(f"word_count={wc} ok={ok}", flush=True)
        if not ok:
            print("FAIL: empty report or word_count", r.get("errors"), flush=True)
            return 1
    print("\nAll regression queries passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
