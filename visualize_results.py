"""
visualize_results.py

Runs every scenario from offline_governed_agent_demo.py through the real
governance gate and draws one timeline image (docs/results.png), so the
outcome of each case can be read at a glance. No extra data is invented here:
every block in the picture is a row that the audit log actually recorded.

Run:
    pip install matplotlib
    python3 visualize_results.py
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, FancyBboxPatch

import offline_governed_agent_demo as demo

CASES = [
    ("normal_job",      "Case 1  Normal job",
     "All gates pass, asset delivered"),
    ("oversized_job",   "Case 2  Oversized scan (1200 MB)",
     "Size cap blocks compression, agent escalates to a human"),
    ("skip_validation", "Case 3  Deliver without validation",
     "State check blocks delivery, no validation on record"),
    ("delete_attempt",  "Case 4  Delete client's raw scan",
     "Hard block, this tool can never run"),
    ("rapid_fire",      "Case 5  Burst of 8 calls",
     "First 5 allowed, last 3 rate limited"),
]
COLORS = {"ALLOWED": "#2E7D32", "BLOCKED": "#C0392B", "RATE_LIMITED": "#D68910"}
SHORT = {
    "ingest_asset": "ingest",
    "select_compression_profile": "select\nprofile",
    "run_compression": "comp-\nress",
    "validate_fidelity": "validate",
    "deliver_to_client": "deliver",
    "flag_for_manual_review": "flag for\nhuman",
    "purge_original_source_file": "purge\noriginal",
}

def run_all():
    out = []
    for key, title, note in CASES:
        demo.RECENT_CALL_TIMES.clear()
        demo.COMPRESSED_ASSETS.clear()
        demo.VALIDATED_ASSETS.clear()
        steps = []
        for tool, args in demo.mock_agent_plan(key):
            before = len(demo.AUDIT_LOG)
            demo.run_tool_with_governance(tool, args)
            decision = demo.AUDIT_LOG[before]["decision"]
            steps.append((tool, decision))
        out.append((title, note, steps))
    return out

def draw(results, path):
    max_steps = max(len(s) for _, _, s in results)
    fig, ax = plt.subplots(figsize=(17, 7.6))
    ax.set_xlim(-7.4, max_steps + 7.4)
    ax.set_ylim(-1.3, len(results) + 0.9)
    ax.axis("off")
    ax.text(-7.4, len(results) + 0.55,
            "Governed agent demo: what the gate decided, step by step",
            fontsize=16, fontweight="bold", va="center")
    ax.text(-7.4, len(results) + 0.15,
            "Each block is one tool call proposed by the agent. Color shows the governance decision recorded in the audit log.",
            fontsize=10, color="#444", va="center")

    for row, (title, note, steps) in enumerate(results):
        y = len(results) - 1 - row
        ax.text(-7.4, y, title, fontsize=11, fontweight="bold", va="center")
        for i, (tool, decision) in enumerate(steps):
            box = FancyBboxPatch((i + 0.06, y - 0.36), 0.88, 0.72,
                                 boxstyle="round,pad=0.02,rounding_size=0.08",
                                 fc=COLORS[decision], ec="white", lw=1.5)
            ax.add_patch(box)
            ax.text(i + 0.5, y, SHORT.get(tool, tool), color="white",
                    fontsize=7.5, ha="center", va="center", fontweight="bold")
        ax.text(max_steps + 0.3, y, note, fontsize=9.5, va="center", color="#222")

    counts = {k: 0 for k in COLORS}
    for _, _, steps in results:
        for _, d in steps:
            counts[d] += 1
    total = sum(counts.values())
    ax.text(-7.4, -0.95,
            f"Totals across {total} proposed calls:  "
            f"{counts['ALLOWED']} allowed,  {counts['BLOCKED']} blocked,  {counts['RATE_LIMITED']} rate limited",
            fontsize=11, fontweight="bold")
    ax.legend(handles=[Patch(color=c, label=k.replace("_", " ").title()) for k, c in COLORS.items()],
              loc="lower right", ncol=3, frameon=False, fontsize=10,
              bbox_to_anchor=(1.0, 0.0))
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)

if __name__ == "__main__":
    import os
    os.makedirs("docs", exist_ok=True)
    draw(run_all(), "docs/results.png")
    print("Saved docs/results.png")
