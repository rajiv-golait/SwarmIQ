"""Run pipeline and write result to file (T6 smoke test).

Set thread env vars before any project imports so PyTorch/OpenMP see them on Windows.
"""
import os
import sys

for _k, _v in (
    ("OMP_NUM_THREADS", "1"),
    ("MKL_NUM_THREADS", "1"),
    ("TOKENIZERS_PARALLELISM", "false"),
):
    os.environ.setdefault(_k, _v)

sys.path.insert(0, ".")


def _progress(msg: str) -> None:
    print(msg, flush=True)


def _on_phase(entry: str) -> None:
    _progress(f"  [phase] {entry}")


import traceback  # noqa: E402

result_lines: list[str] = []

try:
    _progress("Importing pipeline (first run may download embedding model)...")
    from agents.graph import run_pipeline  # noqa: E402

    _progress(
        "Running full pipeline for: What is LangGraph? "
        "(DDG search + Jina can take several minutes; console is quiet if you use *> file.log.)"
    )
    result = run_pipeline("What is LangGraph?", event_callback=_on_phase)
    result_lines.append("Starting pipeline...")
    result_lines.append(f"SUCCESS word_count: {result.get('word_count', 0)}")
    result_lines.append(f"SUCCESS report_len: {len(result.get('report', ''))}")
    result_lines.append(f"SUCCESS report_preview: {result.get('report', '')[:500]}")
    result_lines.append(f"phase_log: {result.get('phase_log', [])}")
    result_lines.append(f"errors: {result.get('errors', [])}")
except Exception as e:
    result_lines.append(f"PIPELINE ERROR: {e}")
    result_lines.append(traceback.format_exc())

with open("pipeline_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(result_lines))

_progress("--- done --- (see pipeline_result.txt; full log if you used *> file.log)")
print("\n".join(result_lines))
