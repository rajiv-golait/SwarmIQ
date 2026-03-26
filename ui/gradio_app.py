from pathlib import Path
import sys
import tempfile
import os

import gradio as gr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.supervisor import Supervisor
from evaluation.coherence_scorer import CoherenceScorer
from utils.config import SWARM_MODE, SWARM_RUNTIME

try:
    from markdown_pdf import MarkdownPdf, Section
    MARKDOWN_PDF_AVAILABLE = True
except ImportError:
    MARKDOWN_PDF_AVAILABLE = False


APP_CSS = """
.gradio-container {
  background: radial-gradient(circle at 10% 0%, #111522 0%, #0a0b0f 35%) !important;
  color: #e7ecf7 !important;
}
#app-shell {
  max-width: 1480px;
  margin: 0 auto;
  min-height: 92vh;
  padding: 12px 10px 18px 10px !important;
}
#left-panel, #right-panel {
  background: rgba(14, 18, 27, 0.92);
  border: 1px solid #1c2432;
  border-radius: 18px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}
#left-panel {
  padding: 16px !important;
  min-height: 88vh;
}
#right-panel {
  padding: 10px 12px 12px 12px !important;
  min-height: 88vh;
}
#app-title {
  margin: 2px 0 6px 0;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: 0.2px;
}
#app-subtitle {
  margin: 0 0 10px 0;
  font-size: 12px;
  color: #98a2b4;
}
.chip-row {
  font-size: 11px;
  color: #aeb8c8;
  margin-bottom: 12px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #0d1119;
  border: 1px solid #202a39;
}
.control-card {
  background: #0b0f16;
  border: 1px solid #202a3a;
  border-radius: 12px;
  padding: 8px;
  margin-top: 10px;
}
.compact-btn button {
  border-radius: 12px !important;
  font-weight: 500 !important;
}
.ghost-btn button {
  background: #111826 !important;
  border: 1px solid #2a3447 !important;
  color: #d6deed !important;
}
.primary-btn button {
  background: linear-gradient(180deg, #3c7bff 0%, #2a66ff 100%) !important;
  border: 1px solid #2a66ff !important;
  color: #ffffff !important;
}
.gr-textbox label, .gr-markdown h1, .gr-markdown h2, .gr-markdown h3 {
  color: #e7ecf7 !important;
}
.gr-textbox textarea {
  background: #0b0f16 !important;
  color: #e7ecf7 !important;
  border: 1px solid #222c3d !important;
  border-radius: 12px !important;
  font-size: 14px !important;
}
.gr-button {
  min-height: 44px !important;
}
.gr-tab-nav button {
  font-size: 12px !important;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
.gr-tab-nav {
  background: #0b0f16 !important;
  border: 1px solid #1f2a3a !important;
  border-radius: 12px !important;
  padding: 4px !important;
}
.gr-markdown {
  font-size: 14px !important;
  line-height: 1.55 !important;
}
#run-status textarea {
  background: #0b0f16 !important;
  border: 1px solid #202a3a !important;
  border-radius: 10px !important;
  font-size: 12px !important;
}
"""


def format_negotiation_log(negotiation_log: list) -> str:
    if not negotiation_log:
        return "No negotiation rounds recorded."

    lines = []
    for round_data in negotiation_log:
        round_num = round_data.get("round", 0)
        claims = round_data.get("claims_reviewed", [])
        outcomes = round_data.get("outcomes", {})
        unresolved = round_data.get("unresolved", [])
        lines.append(f"**Round {round_num}**")
        lines.append(f"- Claims reviewed: {len(claims)}")
        lines.append(f"- Resolved: {len(outcomes)}")
        lines.append(f"- Unresolved: {len(unresolved)}")
        for claim_id, outcome in outcomes.items():
            lines.append(f"  - `{claim_id[:12]}...`: {outcome}")
        lines.append("")
    return "\n".join(lines)


def format_visualization(viz_data: dict | None) -> str:
    if not viz_data:
        return "No visualization generated."

    viz_type = viz_data.get("type", "unknown")
    if viz_type == "mermaid_timeline":
        mermaid = viz_data.get("visualization", "")
        return f"```mermaid\n{mermaid}\n```"
    if viz_type == "table":
        table_data = viz_data.get("visualization", [])
        if not table_data:
            return "No table data available."
        lines = ["| Claim | Confidence | Evidence Count |", "|---|---:|---:|"]
        for row in table_data:
            claim = row.get("claim", "N/A")[:56]
            confidence = row.get("confidence", 0)
            ev_count = row.get("evidence_count", 0)
            lines.append(f"| {claim} | {confidence:.2f} | {ev_count} |")
        return "\n".join(lines)
    return f"Unknown visualization type: {viz_type}"


def extract_doc_only(report_with_meta: str) -> str:
    """Extract just the research document without the run summary metadata."""
    # Find the Run Summary section and remove it
    parts = report_with_meta.split("---\n\n### Run Summary")
    if len(parts) > 1:
        doc_only = parts[0].strip()
        return doc_only
    return report_with_meta


def create_export_files(report_doc: str, query: str) -> tuple[str | None, str | None]:
    """Create markdown and PDF export files. Returns (md_path, pdf_path)."""
    md_path = None
    pdf_path = None

    # Create temporary files
    temp_dir = tempfile.gettempdir()
    safe_query = "".join(c for c in query[:50] if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_query = safe_query.replace(' ', '_') or 'research_report'

    # Save Markdown
    try:
        md_path = os.path.join(temp_dir, f"{safe_query}.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(report_doc)
    except Exception as e:
        print(f"Error creating markdown file: {e}")

    # Save PDF if markdown-pdf is available
    if MARKDOWN_PDF_AVAILABLE and md_path:
        try:
            pdf_path = os.path.join(temp_dir, f"{safe_query}.pdf")
            pdf = MarkdownPdf(toc_level=2)
            pdf.add_section(Section(report_doc, toc=False))
            pdf.save(pdf_path)
        except Exception as e:
            print(f"Error creating PDF: {e}")
            pdf_path = None

    return md_path, pdf_path


def run_swarmiq(query: str, advanced_mode: bool = False):
    if not query or not query.strip():
        return (
            "Please enter a valid research query.",
            "No run started.",
            "No visualization.",
            "Idle",
            None,  # md_file
            None,  # pdf_file
        )

    supervisor = Supervisor()
    result = supervisor.run(query)

    scorer = CoherenceScorer()
    score_result = scorer.score(query, result["report"], result["sources"])

    sources_block = "\n".join(result["sources"]) if result["sources"] else "No sources found."
    log_block = "\n".join(result["session_log"]) if result["session_log"] else "No logs recorded."
    score_label = "PASSED" if score_result["passed"] else "BELOW THRESHOLD"
    conflicts_label = "Yes" if result["conflicts_detected"] else "No"
    mode_label = (
        "AUTONOMOUS SWARM"
        if SWARM_MODE and SWARM_RUNTIME == "autonomous"
        else ("SEQUENTIAL SWARM" if SWARM_MODE else "LEGACY")
    )

    stage_events = result.get("stage_events", [])
    stage_block = (
        "\n".join(
            [
                f"- {event.get('timestamp', '')} | {event.get('stage', '').upper()}: {event.get('message', '')}"
                for event in stage_events
            ]
        )
        if stage_events
        else "No stage events recorded."
    )

    citation_validation = result.get("citation_validation", {})
    citation_state = "PASSED" if citation_validation.get("ok") else "FAILED"
    claims_summary = result.get("claims_summary", {})
    claims_block = (
        f"Total `{claims_summary.get('total', 0)}` | Accepted `{claims_summary.get('accepted', 0)}` | "
        f"Rejected `{claims_summary.get('rejected', 0)}` | Uncertain `{claims_summary.get('uncertain', 0)}`"
        if claims_summary
        else "Claims data unavailable in legacy mode."
    )
    negotiation_log = result.get("negotiation_log", [])
    negotiation_rounds = result.get("negotiation_rounds", 0)
    negotiation_block = format_negotiation_log(negotiation_log)
    viz_block = format_visualization(result.get("visualization"))

    # Core research document (what gets exported)
    doc_only = result['report']

    # Full report with metadata (shown in UI when advanced mode is on)
    report_with_meta = (
        f"{doc_only}\n\n"
        "---\n\n"
        "### Run Summary\n\n"
        f"- Mode: **{mode_label}**\n"
        f"- Claims: {claims_block}\n"
        f"- Negotiation rounds: **{negotiation_rounds}**\n"
        f"- Conflicts detected: **{conflicts_label}**\n"
        f"- Coherence score: **{score_result['score']:.2f}** ({score_label})\n"
        f"- Citation validation: **{citation_state}** ({citation_validation.get('reason', 'N/A')})\n"
        f"- Word count: **{result['word_count']}**\n\n"
        "### Sources\n"
        f"{sources_block}\n"
    )

    negotiation_output = (
        "## Negotiation & Consensus\n\n"
        f"{negotiation_block}\n\n"
        "## Stage Progress\n\n"
        f"{stage_block}\n\n"
        "## Agent Log\n\n"
        f"{log_block}"
    )

    status = (
        f"Completed in {len(stage_events)} stages | "
        f"Mode: {mode_label} | "
        f"Citations: {citation_state}"
    )

    # Create export files
    md_path, pdf_path = create_export_files(doc_only, query)

    # Return different outputs based on advanced mode
    if advanced_mode:
        return report_with_meta, negotiation_output, viz_block, status, md_path, pdf_path
    else:
        # In simple mode, return clean report and hide internals
        return doc_only, "_HIDDEN_", "_HIDDEN_", status, md_path, pdf_path


with gr.Blocks(css=APP_CSS, theme=gr.themes.Base(), title="SwarmIQ") as demo:
    with gr.Row(elem_id="app-shell"):
        with gr.Column(scale=3, min_width=320, elem_id="left-panel"):
            gr.Markdown("## SwarmIQ", elem_id="app-title")
            gr.Markdown(
                "Minimal research workspace for autonomous multi-agent runs.",
                elem_id="app-subtitle",
            )
            gr.Markdown(
                f"<div class='chip-row'>Runtime: <b>{SWARM_RUNTIME}</b> | Swarm mode: <b>{'on' if SWARM_MODE else 'off'}</b></div>"
            )

            query_input = gr.Textbox(
                label="Research Query",
                placeholder="e.g. Climate policy updates COP30",
                lines=5,
            )

            with gr.Row():
                run_btn = gr.Button("Run Swarm", variant="primary", elem_classes=["compact-btn", "primary-btn"])
                clear_btn = gr.Button("Clear", elem_classes=["compact-btn", "ghost-btn"])

            with gr.Group(elem_classes=["control-card"]):
                gr.Examples(
                    examples=[
                        ["Climate policy updates COP30"],
                        ["Latest AI regulations in India 2025"],
                        ["Digital health policy in India"],
                    ],
                    inputs=query_input,
                    label="Quick prompts",
                )

            # Advanced mode toggle (default unchecked = hidden internals)
            advanced_checkbox = gr.Checkbox(
                label="Show Advanced / Agent Internals",
                value=False,
                info="Show negotiation logs, stage progress, and visualizations",
            )

            status_box = gr.Textbox(
                label="Run Status",
                interactive=False,
                lines=2,
                value="Idle",
                elem_id="run-status",
            )

            # Export buttons
            with gr.Group(elem_classes=["control-card"]):
                gr.Markdown("### Export Research Document")
                md_export = gr.File(
                    label="Download Markdown",
                    interactive=False,
                    visible=True,
                )
                pdf_export = gr.File(
                    label="Download PDF",
                    interactive=False,
                    visible=MARKDOWN_PDF_AVAILABLE,
                )

        with gr.Column(scale=9, min_width=760, elem_id="right-panel"):
            with gr.Tabs() as tabs:
                with gr.Tab("Report", id="report") as report_tab:
                    report_out = gr.Markdown(value="Waiting for a research run...")
                with gr.Tab("Negotiation", id="negotiation", visible=False) as negotiation_tab:
                    negotiation_out = gr.Markdown(value="")
                with gr.Tab("Visualization", id="viz", visible=False) as visualization_tab:
                    viz_out = gr.Markdown(value="")

    # Event handlers
    run_btn.click(
        fn=run_swarmiq,
        inputs=[query_input, advanced_checkbox],
        outputs=[report_out, negotiation_out, viz_out, status_box, md_export, pdf_export],
    )

    clear_btn.click(
        fn=lambda: ("", "_HIDDEN_", "_HIDDEN_", "Idle", "", None, None),
        inputs=[],
        outputs=[report_out, negotiation_out, viz_out, status_box, query_input, md_export, pdf_export],
    )

    # Update visibility when checkbox changes
    advanced_checkbox.change(
        fn=lambda advanced: (gr.update(visible=advanced), gr.update(visible=advanced)),
        inputs=[advanced_checkbox],
        outputs=[negotiation_tab, visualization_tab],
    )


if __name__ == "__main__":
    import os

    port = int(os.getenv("PORT", "7860"))
    demo.launch(server_name="0.0.0.0", server_port=port)
