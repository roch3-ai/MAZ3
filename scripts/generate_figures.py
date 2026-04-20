"""Figure generation for Paper 1 v4.5.

Outputs:
  figures/fig1_five_phase_loop.{svg,png}        - Syncference protocol cycle
  figures/fig2_gamma_operator.{svg,png}         - Three composition rules
  figures/fig3_hp_vs_network.png                - H_p vs network (data)
  figures/fig4_mvr_schema.{svg,png}             - 5-field MVR structure
  figures/fig5_asymmetric_risk_layout.{svg,png} - Scenario layout

Run: python scripts/generate_figures.py --fig {1|2|3|4|5|all}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import (Circle, Ellipse, FancyArrowPatch,
                                 FancyBboxPatch, Rectangle)

PRIMARY = "#1f4e79"
ACCENT = "#d97706"
ACCENT_FILL = "#fff7ed"
NEUTRAL_DARK = "#222222"
NEUTRAL_MID = "#555555"
NEUTRAL_LIGHT = "#bbbbbb"

FIG_DIR = Path(__file__).resolve().parent.parent / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "mathtext.fontset": "cm",
    "axes.edgecolor": NEUTRAL_DARK,
    "axes.labelcolor": NEUTRAL_DARK,
    "xtick.color": NEUTRAL_DARK,
    "ytick.color": NEUTRAL_DARK,
    "pdf.fonttype": 42,
    "svg.fonttype": "path",
})


def save_fig(fig, name, *, dpi=300, svg=True):
    png_path = FIG_DIR / f"{name}.png"
    fig.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    print(f"  wrote {png_path.relative_to(FIG_DIR.parent)}")
    if svg:
        svg_path = FIG_DIR / f"{name}.svg"
        fig.savefig(svg_path, bbox_inches="tight", facecolor="white")
        print(f"  wrote {svg_path.relative_to(FIG_DIR.parent)}")


def fig1_five_phase_loop():
    fig, ax = plt.subplots(figsize=(8.5, 8.5))
    ax.set_aspect("equal")
    ax.set_xlim(-5.8, 5.8)
    ax.set_ylim(-5.8, 5.8)
    ax.axis("off")

    r = 3.9
    phases = [
        ("Sense",   90),
        ("Project", 18),
        ("Compose", -54),
        ("Infer",  -126),
        ("Act",    162),
    ]
    subs = {
        "Sense":   "perceive local world",
        "Project": "compress to MVR",
        "Compose": r"merge via $\Gamma$",
        "Infer":   r"consult $M^*$",
        "Act":     "execute action",
    }
    positions = []
    for _, deg in phases:
        rad = np.deg2rad(deg)
        positions.append((r * np.cos(rad), r * np.sin(rad)))

    # Phase nodes
    node_w, node_h = 2.1, 1.15
    for (x, y), (name, _) in zip(positions, phases):
        ax.add_patch(FancyBboxPatch(
            (x - node_w / 2, y - node_h / 2), node_w, node_h,
            boxstyle="round,pad=0.06,rounding_size=0.18",
            linewidth=1.6, edgecolor=NEUTRAL_DARK, facecolor="white", zorder=3,
        ))
        ax.text(x, y + 0.22, name, ha="center", va="center",
                fontsize=15, fontweight="bold", color=NEUTRAL_DARK, zorder=4)
        ax.text(x, y - 0.22, subs[name], ha="center", va="center",
                fontsize=10, color=NEUTRAL_MID, style="italic", zorder=4)

    # Central M* node
    c_w, c_h = 2.6, 1.25
    ax.add_patch(FancyBboxPatch(
        (-c_w / 2, -c_h / 2), c_w, c_h,
        boxstyle="round,pad=0.08,rounding_size=0.20",
        linewidth=1.8, edgecolor=ACCENT, facecolor=ACCENT_FILL, zorder=3,
    ))
    ax.text(0, 0.24, "Shared coordination",
            ha="center", va="center", fontsize=10, color=NEUTRAL_MID, zorder=4)
    ax.text(0, 0.02, "surface",
            ha="center", va="center", fontsize=10, color=NEUTRAL_MID, zorder=4)
    ax.text(0, -0.30, r"$M^*$",
            ha="center", va="center", fontsize=22, color=ACCENT,
            fontweight="bold", zorder=4)

    # Cycle arrows (Sense→Project→Compose and Infer→Act→Sense are direct;
    # Compose→Infer is routed through M*)
    edge_labels = {
        ("Sense",   "Project"): r"$W_i$",
        ("Project", "Compose"): r"$\mathrm{MVR}_i=\pi_i(W_i)$",
        ("Infer",   "Act"):     r"$a_i=\mathrm{act}(M^*,p_i)$",
        ("Act",     "Sense"):   r"$W'$  (world evolves)",
    }
    names = [p[0] for p in phases]
    for i in range(5):
        a_name, b_name = names[i], names[(i + 1) % 5]
        if (a_name, b_name) not in edge_labels:
            continue
        a, b = positions[i], positions[(i + 1) % 5]
        rad = -0.18
        ax.add_patch(FancyArrowPatch(
            a, b, arrowstyle="-|>", mutation_scale=16,
            linewidth=1.5, color=NEUTRAL_DARK,
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=46, shrinkB=46, zorder=2,
        ))
        # Label at outward-offset midpoint
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        rlen = np.hypot(mx, my)
        nx, ny = (mx / rlen, my / rlen) if rlen > 0 else (0.0, 1.0)
        off = 1.15
        ax.text(mx + nx * off, my + ny * off,
                edge_labels[(a_name, b_name)],
                ha="center", va="center", fontsize=11,
                color=PRIMARY, zorder=5)

    # Compose → M* and M* → Infer (accent-colored bridges)
    compose_pos = positions[2]
    infer_pos = positions[3]
    ax.add_patch(FancyArrowPatch(
        compose_pos, (0, 0), arrowstyle="-|>", mutation_scale=14,
        linewidth=1.5, color=ACCENT,
        shrinkA=46, shrinkB=48, zorder=2,
    ))
    ax.add_patch(FancyArrowPatch(
        (0, 0), infer_pos, arrowstyle="-|>", mutation_scale=14,
        linewidth=1.5, color=ACCENT,
        shrinkA=48, shrinkB=46, zorder=2,
    ))
    # Accent-arrow labels (white bbox to interrupt arrow line)
    label_bbox = dict(boxstyle="round,pad=0.18", facecolor="white",
                      edgecolor="none")
    ax.text(1.25, -1.45, r"$\Gamma(\{\mathrm{MVR}_i\})$",
            ha="center", va="center", fontsize=11, color=ACCENT,
            zorder=6, bbox=label_bbox)
    ax.text(-1.25, -1.45, r"read $M^*$",
            ha="center", va="center", fontsize=11, color=ACCENT,
            zorder=6, bbox=label_bbox)

    fig.tight_layout()
    save_fig(fig, "fig1_five_phase_loop", dpi=300)
    plt.close(fig)


def _setup_gamma_panel(ax, title):
    """Shared setup for a single Γ-operator panel."""
    ax.set_aspect("equal")
    ax.set_xlim(-5.0, 5.0)
    ax.set_ylim(-2.2, 2.2)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(title, fontsize=13, fontweight="bold",
                 color=NEUTRAL_DARK, pad=10)
    # Arrow between input region and output region
    ax.add_patch(FancyArrowPatch(
        (-0.6, 0), (0.9, 0), arrowstyle="-|>", mutation_scale=16,
        linewidth=1.6, color=NEUTRAL_DARK, zorder=4,
    ))


def fig2_gamma_operator():
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.22, top=0.90,
                        wspace=0.08)

    input_colors = ["#93c5fd", "#fcd9a5", "#c7cbd1"]  # pale blue / orange / gray

    formulas = [
        r"$M^*.\mathrm{space}=\bigcup_i\,\mathrm{MVR}_i.\mathrm{space}$",
        r"$M^*.\mathrm{constraints}=\bigcap_i\,\mathrm{MVR}_i.\mathrm{constraints}$",
        r"$M^*.\mathrm{risk}(c)=\max_i\,\mathrm{MVR}_i.\mathrm{risk}(c)$",
    ]

    # ---------- Panel A: Spatial union ----------
    axA = axes[0]
    _setup_gamma_panel(axA, "A. Spatial union")
    env_centers = [(-3.2, 0.5), (-2.3, -0.3), (-3.6, -0.7)]
    env_sizes = [(1.7, 1.1), (1.8, 1.3), (1.5, 1.0)]
    for (cx, cy), (w, h), col in zip(env_centers, env_sizes, input_colors):
        axA.add_patch(Ellipse((cx, cy), w, h, facecolor=col,
                              edgecolor=col, alpha=0.75, zorder=2))
    axA.text(-3.0, 1.7, r"$\mathrm{MVR}_i.\mathrm{space}$",
             ha="center", va="center", fontsize=10,
             color=NEUTRAL_MID, style="italic")
    axA.add_patch(Ellipse((3.0, -0.1), 3.1, 2.3,
                          facecolor=ACCENT_FILL, edgecolor=ACCENT,
                          linewidth=2.0, zorder=2))
    axA.text(3.0, 1.7, r"$M^*.\mathrm{space}$",
             ha="center", va="center", fontsize=10,
             color=ACCENT, style="italic")

    # ---------- Panel B: Constraint intersection ----------
    axB = axes[1]
    _setup_gamma_panel(axB, "B. Constraint intersection")
    venn_centers = [(-3.0, 0.55), (-2.2, -0.35), (-3.8, -0.35)]
    for (cx, cy), col in zip(venn_centers, input_colors):
        axB.add_patch(Circle((cx, cy), 1.0, facecolor=col,
                             edgecolor=col, alpha=0.55, zorder=2))
        axB.add_patch(Circle((cx, cy), 1.0, facecolor="none",
                             edgecolor=NEUTRAL_MID, linewidth=0.8, zorder=3))
    axB.text(-3.0, 1.7, r"$\mathrm{MVR}_i.\mathrm{constraints}$",
             ha="center", va="center", fontsize=10,
             color=NEUTRAL_MID, style="italic")
    axB.add_patch(Circle((3.0, -0.05), 0.55, facecolor=ACCENT_FILL,
                         edgecolor=ACCENT, linewidth=2.0, zorder=2))
    axB.text(3.0, 1.7, r"$M^*.\mathrm{constraints}$",
             ha="center", va="center", fontsize=10,
             color=ACCENT, style="italic")

    # ---------- Panel C: Risk maximum ----------
    axC = axes[2]
    _setup_gamma_panel(axC, "C. Risk maximum")
    rng = np.random.default_rng(7)
    grids = [rng.random((3, 3)) for _ in range(3)]
    max_grid = np.maximum.reduce(grids)
    cmap = plt.get_cmap("YlOrRd")
    vmin, vmax = 0.0, 1.0
    # Three separate input mini-grids with gaps between them
    grid_w = 1.10
    grid_h = 1.40
    gap = 0.18
    start_x = -4.4
    grid_y_bot = -0.70
    grid_y_top = grid_y_bot + grid_h
    for i, g in enumerate(grids):
        x0 = start_x + i * (grid_w + gap)
        x1 = x0 + grid_w
        axC.imshow(g, extent=(x0, x1, grid_y_bot, grid_y_top),
                   cmap=cmap, vmin=vmin, vmax=vmax,
                   aspect="auto", zorder=2, interpolation="nearest")
        axC.add_patch(Rectangle((x0, grid_y_bot), grid_w, grid_h,
                                facecolor="none", edgecolor=NEUTRAL_MID,
                                linewidth=0.8, zorder=3))
    axC.text(start_x + 1.5 * (grid_w + gap) - gap / 2, 1.7,
             r"$\mathrm{MVR}_i.\mathrm{risk}$",
             ha="center", va="center", fontsize=10,
             color=NEUTRAL_MID, style="italic")
    # Output: max grid (larger for emphasis)
    out_w, out_h = 1.8, 1.8
    out_x0 = 3.0 - out_w / 2
    out_y0 = -out_h / 2
    axC.imshow(max_grid, extent=(out_x0, out_x0 + out_w, out_y0, out_y0 + out_h),
               cmap=cmap, vmin=vmin, vmax=vmax,
               aspect="auto", zorder=2, interpolation="nearest")
    axC.add_patch(Rectangle((out_x0, out_y0), out_w, out_h,
                            facecolor="none", edgecolor=ACCENT,
                            linewidth=2.0, zorder=3))
    axC.text(3.0, 1.7, r"$M^*.\mathrm{risk}$",
             ha="center", va="center", fontsize=10,
             color=ACCENT, style="italic")
    # Re-assert equal aspect (imshow with aspect="auto" disables it)
    axC.set_aspect("equal")
    axC.set_xlim(-5.0, 5.0)
    axC.set_ylim(-2.2, 2.2)

    fig.canvas.draw()  # force layout pass before computing formula positions

    # Formulas centered under each panel (figure-level text aligned with axes)
    for ax, formula in zip(axes, formulas):
        bbox = ax.get_position()
        x_center = (bbox.x0 + bbox.x1) / 2
        fig.text(x_center, 0.06, formula, ha="center", va="center",
                 fontsize=11, color=NEUTRAL_DARK)

    save_fig(fig, "fig2_gamma_operator", dpi=300)
    plt.close(fig)


def _load_benchmark():
    path = Path(__file__).resolve().parent.parent / "results" / "paper1_v4_benchmark_N500.json"
    rows = json.loads(path.read_text())
    index = {}
    for r in rows:
        index[(r["scenario"], r["network"], r["agent_type"])] = r
    return index


def fig3_hp_vs_network():
    data = _load_benchmark()
    networks = ["ideal", "wifi_warehouse", "lora_mesh"]
    labels = ["Ideal", "WiFi\nwarehouse", "LoRa\nmesh"]
    x_pos = np.arange(len(networks))

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    scenarios = [("bottleneck", "Bottleneck"),
                 ("asymmetric_risk", "Asymmetric-Risk")]

    for ax, (scen_key, scen_label) in zip(axes, scenarios):
        sync = [data[(scen_key, nw, "syncference")] for nw in networks]
        omni = [data[(scen_key, nw, "omniscient_v2")] for nw in networks]

        ax.errorbar(x_pos, [r["hp_mean"] for r in sync],
                    yerr=[r["hp_std"] for r in sync],
                    fmt="-o", color=PRIMARY, ecolor=PRIMARY,
                    capsize=4, lw=1.8, markersize=7,
                    label="Syncference", zorder=4)
        ax.errorbar(x_pos, [r["hp_mean"] for r in omni],
                    yerr=[r["hp_std"] for r in omni],
                    fmt="-s", color=ACCENT, ecolor=ACCENT,
                    capsize=4, lw=1.8, markersize=7,
                    label=r"Omniscient-$\Gamma$-lossless", zorder=4)

        if scen_key == "bottleneck":
            ax.axhline(sync[0]["hp_mean"], ls=":", color=PRIMARY,
                       alpha=0.55, lw=1.0, zorder=2)
            ax.axhline(omni[0]["hp_mean"], ls=":", color=ACCENT,
                       alpha=0.55, lw=1.0, zorder=2)

        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels)
        ax.set_title(scen_label, fontsize=13, fontweight="bold",
                     color=NEUTRAL_DARK, pad=6)
        ax.set_xlabel("Network profile", fontsize=11)
        ax.yaxis.grid(True, color=NEUTRAL_LIGHT, lw=0.6, alpha=0.6)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xlim(-0.3, 2.3)

    axes[0].set_ylabel(r"$H_p$  (coordination quality)", fontsize=11)
    axes[0].set_ylim(0.60, 1.03)
    axes[0].legend(loc="lower left", frameon=False, fontsize=10)

    fig.tight_layout()
    save_fig(fig, "fig3_hp_vs_network", dpi=300, svg=False)
    plt.close(fig)


def fig4_mvr_schema():
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.set_aspect("equal")
    ax.set_xlim(-5.8, 5.8)
    ax.set_ylim(-5.2, 5.2)
    ax.axis("off")

    # Central MVR_i hub
    cw, ch = 2.6, 1.35
    ax.add_patch(FancyBboxPatch(
        (-cw / 2, -ch / 2), cw, ch,
        boxstyle="round,pad=0.08,rounding_size=0.20",
        linewidth=2.0, edgecolor=ACCENT, facecolor=ACCENT_FILL, zorder=3,
    ))
    ax.text(0, 0.22, r"$\mathrm{MVR}_i$", ha="center", va="center",
            fontsize=22, fontweight="bold", color=ACCENT, zorder=4)
    ax.text(0, -0.30, "5-field projection",
            ha="center", va="center", fontsize=10,
            color=NEUTRAL_MID, style="italic", zorder=4)

    # 5 fields at pentagon vertices
    r = 3.7
    fields = [
        (90,   r"$\sigma_i$", "Spatial envelope",
               "convex hull of predicted\nfuture positions",
               r"polygon $\subset \mathbb{R}^2$"),
        (18,   r"$\iota_i$",  "Intent vector",
               "destination or\nvelocity goal",
               r"vector $\in \mathbb{R}^2$"),
        (-54,  r"$\kappa_i$", "Capability",
               "max speed / agility",
               r"scalar $\in \mathbb{R}_{+}$"),
        (-126, r"$\tau_i$",   "Trust signal",
               "current trust score",
               r"scalar $\in [0, 1]$"),
        (162,  r"$\rho_i$",   "Risk field",
               "local risk perception",
               r"field $\mathbb{R}^2 \to [0, 1]$"),
    ]
    node_w, node_h = 2.6, 1.9
    for deg, sym, name, desc, tp in fields:
        rad = np.deg2rad(deg)
        nx, ny = r * np.cos(rad), r * np.sin(rad)
        ax.add_patch(FancyBboxPatch(
            (nx - node_w / 2, ny - node_h / 2), node_w, node_h,
            boxstyle="round,pad=0.06,rounding_size=0.16",
            linewidth=1.4, edgecolor=NEUTRAL_DARK, facecolor="white", zorder=3,
        ))
        ax.text(nx, ny + 0.60, sym, ha="center", va="center",
                fontsize=18, color=PRIMARY, zorder=4)
        ax.text(nx, ny + 0.15, name, ha="center", va="center",
                fontsize=11, fontweight="bold", color=NEUTRAL_DARK, zorder=4)
        ax.text(nx, ny - 0.22, desc, ha="center", va="center",
                fontsize=8.5, color=NEUTRAL_MID, zorder=4)
        ax.text(nx, ny - 0.70, tp, ha="center", va="center",
                fontsize=9, color=NEUTRAL_MID, style="italic", zorder=4)
        # Connector line from MVR_i hub to this field
        ax.add_patch(FancyArrowPatch(
            (0, 0), (nx, ny), arrowstyle="-",
            linewidth=1.1, color=NEUTRAL_LIGHT,
            shrinkA=52, shrinkB=58, zorder=1,
        ))

    save_fig(fig, "fig4_mvr_schema", dpi=300)
    plt.close(fig)


def fig5_asymmetric_risk_layout():
    fig, ax = plt.subplots(figsize=(8.5, 8))
    ax.set_aspect("equal")

    field_size = 50.0
    risk_size = 15.0
    risk_cx, risk_cy = 25.0, 25.0
    sensing_r = 5.0

    ax.set_xlim(-6, field_size + 10)
    ax.set_ylim(-6, field_size + 8)

    # Field boundary
    ax.add_patch(Rectangle((0, 0), field_size, field_size,
                           facecolor="#fafafa", edgecolor=NEUTRAL_DARK,
                           linewidth=1.4, zorder=1))

    # Risk zone
    risk_x0 = risk_cx - risk_size / 2
    risk_y0 = risk_cy - risk_size / 2
    ax.add_patch(Rectangle((risk_x0, risk_y0), risk_size, risk_size,
                           facecolor="#fecaca", edgecolor="#ef4444",
                           linewidth=1.5, alpha=0.65, zorder=2))
    ax.text(risk_cx, risk_y0 + risk_size + 0.8,
            "Risk zone (15 m × 15 m)",
            ha="center", va="bottom", fontsize=10,
            color="#b91c1c", style="italic", zorder=5)

    # Agent definitions: (current_x, y, lane_type, label)
    agents = [
        (20, 10, "outer",  "Agent 1"),
        (20, 40, "outer",  "Agent 2"),
        (20, 22, "center", "Agent 3"),
        (20, 25, "center", "Agent 4"),
        (20, 28, "center", "Agent 5"),
    ]

    for x, y, lane, label in agents:
        # Dotted path from start (2, y) to destination (48, y)
        ax.plot([2, 48], [y, y], ls=(0, (1, 2)),
                color=NEUTRAL_LIGHT, lw=0.9, zorder=2)
        # Start marker
        ax.plot(2, y, "o", color=NEUTRAL_DARK, markersize=3.5, zorder=3)
        # Destination arrow
        ax.add_patch(FancyArrowPatch(
            (45, y), (48, y), arrowstyle="-|>", mutation_scale=11,
            linewidth=1.0, color=NEUTRAL_DARK, zorder=3,
        ))
        # Current-position sensing circle (dashed)
        ax.add_patch(Circle(
            (x, y), sensing_r, facecolor="none",
            edgecolor=PRIMARY, linewidth=1.0,
            linestyle=(0, (3, 2)), alpha=0.75, zorder=4,
        ))
        # Current position
        ax.plot(x, y, "o", color=PRIMARY, markersize=7, zorder=5,
                markeredgecolor="white", markeredgewidth=1.0)
        # Label to the right of the sensing circle
        ax.text(x + sensing_r + 1.2, y, label,
                ha="left", va="center", fontsize=10,
                fontweight="bold" if lane == "center" else "normal",
                color=NEUTRAL_DARK, zorder=5)

    # Lane brackets (far right margin)
    ax.annotate("", xy=(field_size + 3.8, 38),
                xytext=(field_size + 3.8, 42),
                arrowprops=dict(arrowstyle="-", color=NEUTRAL_MID, lw=1.0))
    ax.text(field_size + 4.2, 40, "outer", fontsize=9,
            color=NEUTRAL_MID, style="italic", va="center")
    ax.annotate("", xy=(field_size + 3.8, 8),
                xytext=(field_size + 3.8, 12),
                arrowprops=dict(arrowstyle="-", color=NEUTRAL_MID, lw=1.0))
    ax.text(field_size + 4.2, 10, "outer", fontsize=9,
            color=NEUTRAL_MID, style="italic", va="center")
    ax.annotate("", xy=(field_size + 3.8, 20.5),
                xytext=(field_size + 3.8, 29.5),
                arrowprops=dict(arrowstyle="-", color=NEUTRAL_MID, lw=1.0))
    ax.text(field_size + 4.2, 25, "center", fontsize=9,
            color=NEUTRAL_MID, style="italic", va="center")

    # Inline callouts: sensing radius (top-right of agent 2)
    ax.annotate("sensing radius (5 m)",
                xy=(20 + sensing_r * 0.7, 40 + sensing_r * 0.7),
                xytext=(34, 48),
                fontsize=9, color=PRIMARY,
                arrowprops=dict(arrowstyle="-", color=PRIMARY, lw=0.8,
                                connectionstyle="arc3,rad=0.0"))

    # Start / destination text annotations on left and right edges
    ax.text(2, -2, "start", ha="center", va="top", fontsize=9,
            color=NEUTRAL_MID)
    ax.text(48, -2, "destination", ha="center", va="top", fontsize=9,
            color=NEUTRAL_MID)

    # Axis styling
    ax.set_xlabel("x  (m)", fontsize=11)
    ax.set_ylabel("y  (m)", fontsize=11)
    ax.set_xticks([0, 10, 20, 30, 40, 50])
    ax.set_yticks([0, 10, 20, 30, 40, 50])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(colors=NEUTRAL_MID, labelsize=9)

    fig.tight_layout()
    save_fig(fig, "fig5_asymmetric_risk_layout", dpi=300)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fig", choices=["1", "2", "3", "4", "5", "all"],
                        default="all")
    args = parser.parse_args()

    generators = {
        "1": ("Fig 1 — five-phase loop",     fig1_five_phase_loop),
        "2": ("Fig 2 — gamma operator",      fig2_gamma_operator),
        "3": ("Fig 3 — H_p vs network",      fig3_hp_vs_network),
        "4": ("Fig 4 — MVR schema",          fig4_mvr_schema),
        "5": ("Fig 5 — asymmetric-risk",     fig5_asymmetric_risk_layout),
    }
    targets = list(generators.keys()) if args.fig == "all" else [args.fig]
    for key in targets:
        label, fn = generators[key]
        print(f"[generate_figures] {label}")
        try:
            fn()
        except NotImplementedError as e:
            print(f"  skip: {e}")


if __name__ == "__main__":
    main()
