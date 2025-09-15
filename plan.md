## Implementation Plan: SWE-bench Agent Evaluation Harness (i1–i4)

### Purpose & Success Criteria

- Goal: Rapidly build a small, reproducible harness to evaluate coding agents on a curated subset of SWE-bench and produce a trustworthy leaderboard—without unduly constraining capable agents.
- Success: Harness emits predictions in the official SWE-bench JSONL format and invokes the official evaluator (no custom scoring). i1 shows a clear spread across 4–6 models on 6–8 easy instances; best model ≫ a no-patch baseline; runs are reproducible.
- Scope cadence: i2 adds multi-attempt and more models; i3 adds multi-patch and numpy/pandas tasks; i4 adds token & cost metrics.
- Velocity: Start with short timeouts; increase only when clearly necessary.

### Iterations Overview

#### i1 — Working Slice (fast validation)

- Dataset: SWE-bench Lite. Pin 6–8 “easy one-patch” instances (short gold patches, minimal hunks).
- Agent modes:
  - Patch mode (default): model outputs a unified diff only.
  - Shell mode (enabled, time-budgeted): audited tools (atomic read/write, git diff/apply, targeted `pytest -k`, text search/edit, short Python runner). No outbound network.
- Models (Chutes only):
  - `Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8`
  - `Qwen/Qwen3-Coder-30B-A3B-Instruct`
  - `moonshotai/Kimi-K2-Instruct-0905`
  - `unsloth/gemma-3-12b-it`
  - `zai-org/GLM-4.5-FP8`
  - `zai-org/GLM-4.5-Air`
- Compute policy: Use up to 80% of local CPU (16 threads) ⇒ plan 12 workers by default.
- Concurrency:
  - Predictions: controlled by `WORKERS` env var (default 12); adjust to keep CPU ≤80% and raise only if provider limits allow.
  - Evaluator: `--max_workers` controlled by `EVAL_WORKERS` env var (default 4); increase later if stable.
- Timeouts (aggressive):
  - Per-attempt wall-time: 90s (raise only if too tight).
  - Attempts per instance (K): 2.
  - Per Shell command: 20–30s cap.
- Exit criteria: best model’s resolution rate > baseline; runs reproducible; artifacts complete (predictions, evaluator outputs, logs).

Provider usage policy:
- Prefer Chutes models (≈2,000 daily requests available, free).
- Use OpenRouter sparingly (not free) and only in i2+ experiments when justified.

#### i2 — Scale Models + Multi-Attempt + Leaderboard v1

- Enable multi-attempt per instance (default K=2; allow K=3 where justified).
- Add models (Chutes + OpenRouter; see Model Plan).
- Add triage testing in Shell mode (quick, targeted tests before finalizing the patch).
- Leaderboard v1: pass@1, pass@K, wall-clock, attempts used, tool-call counts. (Tokens/cost deferred to i4.)
- Concurrency: consider evaluator `--max_workers=6–8` if CPU headroom remains.

#### i3 — Harder Tasks (multi-patch + numpy/pandas)

- Expand to 15–20 total instances:
  - Keep the 6–8 easy one-patch items (from i1).
  - Add 6–8 medium multi-patch tasks.
  - Add 3–4 numpy/pandas-heavy tasks (allow longer timeouts if needed).
- Default to Shell mode on multi-patch tasks.
- Leaderboard v2 across ~15–20 models; include per-repo breakdown.

#### i4 — Token & Cost Accounting

- Standardize input/output/total tokens and $-cost across providers.
- Counting priority: provider-reported → official tokenizer → documented approximation.
- Add latency P50/P90/P99.
- Leaderboard v3 = v2 + tokens, cost, latency percentiles (validated against provider dashboards/logs on a sample).

### Architecture (High-Level)

- Provider adapters: Chutes & OpenRouter adapters with uniform chat interface (`model_id`, `temperature`, `max_output`, `seed`, `messages`), retries/backoff, normalized errors. Capture usage metadata when available (store “unknown” otherwise; solved in i4).
- Agent controllers:
  - Patch-mode: enforce diff-only output; validate patch shape; emit `model_patch`.
  - Shell-mode: audited toolbelt; per-command/per-attempt timeouts; export a final diff (vs. base) as `model_patch`.
- Orchestrator: drives N models × M instances × K attempts with concurrency; ensures idempotent resume and thorough logging; produces predictions JSONL and a run manifest.
- Evaluator wrapper: invokes the official evaluator with dataset name, run id, optional `--instance_ids`, `--max_workers`, cache controls; preserves artifacts immutably.
- Selectors: deterministically pick i1/i3 task sets (seeded); persist exact `instance_id`s and dataset revision.
- Metrics & leaderboard: v1/v2 report pass@1, pass@K, wall-time, attempts, tool-calls, run-fail rate; v3 adds tokens, cost, latency.
  - Seeds: `SELECTION_SEED` env var (if set) controls deterministic selection; default 42 if unset.

### Model Plan (by iteration)

- i1 (Chutes only):
  - `Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8`
  - `Qwen/Qwen3-Coder-30B-A3B-Instruct`
  - `moonshotai/Kimi-K2-Instruct-0905`
  - `unsloth/gemma-3-12b-it`
  - `zai-org/GLM-4.5-FP8`
  - `zai-org/GLM-4.5-Air`
- i2 or later (add):
  - `moonshotai/Kimi-Dev-72B`
  - `deepseek-ai/DeepSeek-V3.1`
  - `deepseek-ai/DeepSeek-V3-0324`
  - `deepseek-ai/DeepSeek-R1-0528`
  - `moonshotai/Kimi-K2-Instruct-75k`
  - `Qwen/Qwen3-Next-80B-A3B-Instruct`
  - `chutesai/Mistral-Small-3.2-24B-Instruct-2506`
  - `Qwen/Qwen3-235B-A22B-Thinking-2507`
  - OpenRouter: `openai/gpt-5-mini`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`
- Availability policy: if a model name/endpoint is unavailable or renamed, skip it, record the reason, and continue.

### Instance Selection Policy

- i1: pick very easy one-patch items (short, single-file, few hunks) to fit the 90s attempt cap.
- i3: add multi-patch and numpy/pandas tasks; allow targeted timeout increases only when evidence demands.
- Always pin and commit the exact instance IDs (and dataset revision).

### Compute, Reliability, Observability

- CPU budget: default to 12 workers; scale up/down to keep ≤80% CPU.
- Stability first: increase timeouts/workers only when it improves end-to-end throughput.
- Logging: structured per-attempt logs (prompts redacted as needed), tool-calls, durations, exit codes; evaluator version & dataset revision pinned.
- Idempotence: resume-safe; skip completed (model, instance) cells unless force is set.

### Deliverables by Iteration

- i1: pinned instance list; predictions per model/mode; evaluator artifacts; short validation memo (baseline vs best).
  - Baseline policy: run evaluator with an empty predictions JSONL (0 lines) for the same instances.
  - Pinned instance IDs: `instances/i1_instances_lite.jsonl` (one `instance_id` per line).
  - Selection manifest: `instances/i1_instances_manifest.json` (seed, filters, dataset source).
- i2: multi-attempt config; expanded model list; leaderboard v1 (no tokens).
- i3: 15–20 tasks including multi-patch & numpy/pandas; leaderboard v2.
- i4: token & cost accounting, latency stats; leaderboard v3.
