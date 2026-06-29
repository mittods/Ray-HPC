"""Generate the architecture comparison figure (Fig. 1 in the paper).

Creates a side-by-side comparison diagram of the Celery and Ray stacks.
Output: results/figures/arch_comparison.pdf (copy to hpc/benchmarks/figures/)

Usage:
    python benchmarks/generate_arch_figure.py --output /results/figures/
"""
from __future__ import annotations
import argparse
import os
import sys


def _require_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        return plt, mpatches
    except ImportError:
        print("matplotlib required: pip install matplotlib", file=sys.stderr)
        sys.exit(1)


def draw_box(ax, x, y, w, h, label, color, fontsize=8):
    rect = __import__('matplotlib').patches.FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02",
        linewidth=1.2,
        edgecolor="#333333",
        facecolor=color,
    )
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h / 2, label,
            ha="center", va="center", fontsize=fontsize, fontweight="bold")


def draw_arrow(ax, x1, y1, x2, y2, label=""):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color="#555555", lw=1.2))
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + 0.01, my, label, fontsize=6, color="#555555")


def generate(output_dir: str) -> None:
    plt, mpatches = _require_matplotlib()
    fig, (ax_c, ax_r) = plt.subplots(1, 2, figsize=(8, 4))
    fig.subplots_adjust(wspace=0.4)

    # ── Celery stack ─────────────────────────────────────────────────────────
    ax_c.set_xlim(0, 1)
    ax_c.set_ylim(0, 1)
    ax_c.axis("off")
    ax_c.set_title("Celery (línea base)", fontsize=10, fontweight="bold", pad=8)

    boxes_c = [
        (0.15, 0.82, 0.70, 0.12, "Benchmark Driver\n(Python)", "#AED6F1"),
        (0.15, 0.64, 0.70, 0.12, "Redis Broker", "#F9E79F"),
        (0.00, 0.44, 0.45, 0.12, "Celery Compile\nWorkers × W", "#A9DFBF"),
        (0.52, 0.44, 0.45, 0.12, "Celery Judge\nWorkers × W", "#A9DFBF"),
        (0.15, 0.24, 0.70, 0.12, "PostgreSQL", "#D7BDE2"),
        (0.15, 0.06, 0.70, 0.12, "Artifacts (volumen)", "#EAECEE"),
    ]
    for x, y, w, h, lbl, col in boxes_c:
        draw_box(ax_c, x, y, w, h, lbl, col, fontsize=7)

    draw_arrow(ax_c, 0.50, 0.82, 0.50, 0.76, "dispatch")
    draw_arrow(ax_c, 0.30, 0.64, 0.22, 0.56, "pop")
    draw_arrow(ax_c, 0.70, 0.64, 0.78, 0.56, "pop")
    draw_arrow(ax_c, 0.22, 0.44, 0.40, 0.36, "write DB")
    draw_arrow(ax_c, 0.78, 0.44, 0.60, 0.36, "write DB")
    draw_arrow(ax_c, 0.35, 0.24, 0.35, 0.18, "SQL")
    draw_arrow(ax_c, 0.28, 0.44, 0.40, 0.12, "artifact")

    # ── Ray stack ────────────────────────────────────────────────────────────
    ax_r.set_xlim(0, 1)
    ax_r.set_ylim(0, 1)
    ax_r.axis("off")
    ax_r.set_title("Ray (experimental)", fontsize=10, fontweight="bold", pad=8)

    boxes_r = [
        (0.15, 0.82, 0.70, 0.12, "Ray Driver\n(Python + ray.wait)", "#AED6F1"),
        (0.15, 0.64, 0.70, 0.12, "Ray Scheduler\n(GCS + object store)", "#FDEBD0"),
        (0.00, 0.44, 0.45, 0.12, "@ray.remote\ncompile × W slots", "#A9DFBF"),
        (0.52, 0.44, 0.45, 0.12, "@ray.remote\njudge × W slots", "#A9DFBF"),
        (0.15, 0.24, 0.70, 0.12, "PostgreSQL", "#D7BDE2"),
        (0.15, 0.06, 0.70, 0.12, "Artifacts (volumen)", "#EAECEE"),
    ]
    for x, y, w, h, lbl, col in boxes_r:
        draw_box(ax_r, x, y, w, h, lbl, col, fontsize=7)

    draw_arrow(ax_r, 0.50, 0.82, 0.50, 0.76, "remote()")
    draw_arrow(ax_r, 0.30, 0.64, 0.22, 0.56, "schedule")
    draw_arrow(ax_r, 0.70, 0.64, 0.78, 0.56, "schedule")
    draw_arrow(ax_r, 0.22, 0.44, 0.40, 0.36, "write DB")
    draw_arrow(ax_r, 0.78, 0.44, 0.60, 0.36, "write DB")
    draw_arrow(ax_r, 0.35, 0.24, 0.35, 0.18, "SQL")
    draw_arrow(ax_r, 0.28, 0.44, 0.40, 0.12, "artifact")

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "arch_comparison.pdf")
    fig.savefig(out_path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/results/figures/")
    args = parser.parse_args()
    generate(args.output)
