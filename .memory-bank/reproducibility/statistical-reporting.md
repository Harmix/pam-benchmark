# Statistical Reporting Standards

These rules apply to every numeric claim that leaves the codebase (internal docs, dashboards, customer-facing material, slide decks).

## Minimum Requirements (target state — M2)

- ≥ 3 seeds for any reported mean (≥ 5 preferred). M1 is **single-seed** because the goal is architecture validation, not a publishable comparison; multi-seed lands in M2.
- Report dispersion: std or 95% bootstrap CI (preferred for skewed metrics like latency).
- Significance test for any "better than" claim: paired bootstrap (`src/evals/stats.paired_bootstrap_pvalue`) by default; McNemar for paired classification when more appropriate.
- Multiple-comparison correction (Holm / Bonferroni) when comparing many systems.

## Effect Size

Report effect size, not just p-values: absolute gap with CI, win-rate, or Cohen's d. A statistically significant 0.2-pt gap rarely matters; document the threshold that does.

## Power & Sample Size

If a test set is small, report a power analysis or note the minimum detectable effect so we don't claim parity when the experiment couldn't have detected the gap.

## Tables & Figures

- Bold-best only when the difference is significant.
- Error bars on every plotted mean.
- Color-blind-safe palette; figures rendered at presentation DPI.
- M1's HTML report (`src/reporting/html.py`) does not yet add error bars — the rendering code is in place but values are single-seed; add bars in M2.
