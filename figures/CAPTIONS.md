# Figure captions — Paper 1 v4.5

These captions are written to be pasted directly into the paper markdown at
the sections indicated. Each caption uses the format `![alt](path)` followed
by a descriptive 1–2 line caption line below the image.

---

## Fig 1 — insert after §3 (Protocol Architecture intro)

![Five-phase Syncference loop.](figures/fig1_five_phase_loop.png)

**Figure 1.** The five-phase Syncference protocol cycle. Each agent *i*
senses its local world *W_i*, projects it to a Minimum Viable Representation
*MVR_i = π_i(W_i)*, and the composition operator Γ merges the *{MVR_i}* into
a shared coordination surface *M\**. Agents then infer actions from *M\**
and act, evolving the world before the cycle repeats.

---

## Fig 2 — insert after §3.4 (Composition operator Γ)

![Three composition rules of the Γ operator.](figures/fig2_gamma_operator.png)

**Figure 2.** The Γ operator composes per-agent MVR fields into *M\** via
three type-specific rules: spatial envelopes merge by union (A), constraint
sets merge by intersection (B), and risk fields merge by per-cell maximum (C).
These rules are conservative in the sense that *M\** never relaxes a
constraint or under-reports risk compared to any contributing *MVR_i*.

---

## Fig 3 — insert after §5.2 (Network robustness section)

![H_p vs network profile for Syncference and Omniscient-Γ-lossless across Bottleneck and Asymmetric-Risk, N=500.](figures/fig3_hp_vs_network.png)

**Figure 3.** Coordination quality *H_p* (mean ± std, N = 500) as a function
of network profile for the two scenarios. In Bottleneck (left),
Syncference tracks Omniscient-Γ-lossless under Ideal and WiFi-warehouse
conditions but degrades under LoRa-mesh, crossing below the omniscient
baseline. In Asymmetric-Risk (right), sensing-radius-limited Syncference
pays a persistent sovereignty cost (Δ ≈ −0.29 to −0.35) relative to an
omniscient coordinator with full global risk visibility.

---

## Fig 4 — insert after §3.2 (MVR Schema)

![Five fields of the MVR projection.](figures/fig4_mvr_schema.png)

**Figure 4.** The MVR projection compresses each agent's local world into
five typed fields: the spatial envelope *σ_i* (convex hull of predicted
future positions), the intent vector *ι_i*, the risk field *ρ_i*, the
capability scalar *κ_i*, and the trust signal *τ_i*. Each field is
projected independently and composed via a type-specific rule in Γ.

---

## Fig 5 — insert after §4.2 (Asymmetric-Risk scenario description)

![Top-down layout of the Asymmetric-Risk scenario.](figures/fig5_asymmetric_risk_layout.png)

**Figure 5.** Top-down view of the Asymmetric-Risk scenario. Five agents
traverse a 50 m × 50 m field from left to right; a 15 m × 15 m risk zone
occupies the center. The 5 m sensing radius of outer-lane agents (1, 2)
never reaches the risk zone along their trajectories, while center-lane
agents (3, 4, 5) observe it from within. This asymmetry in local
observability is what prevents Γ-composition from recovering the
omniscient baseline under Syncference.
