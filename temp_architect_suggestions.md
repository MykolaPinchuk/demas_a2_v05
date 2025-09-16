Micro-Tools Editing Approach for SWE-Bench Agents

A small, low-risk interface that removes “malformed patch” & “wrong path” failures without heavy engineering.

Audience: the coding agent (“Codex”) and anyone implementing the harness.
Scope: exact contract, tools, protocol, timeouts, logging, and acceptance gates.
Non-goal: implementation code (this doc is design + instructions only).

1) Why switch from “model prints patch” to “model edits files”

Hand-typed patches are brittle: they force the model to guess paths and reproduce unified-diff syntax perfectly (hunks, context lines, newlines). That’s why you see “no file to patch” and “malformed patch / truncated hunk” errors.

Fix: let the model edit real files via tiny tools, then we generate the canonical patch with git diff. This:

eliminates hunk/format drift (we never ask the model to write a diff),

removes path guessing (the model chooses from an actual repo tree + grep results),

makes “apply check” deterministic (git apply --check tells us exactly what’s wrong).

This approach is a microscopic tool shim (≈200–400 LOC when implemented) with 4–5 simple commands. No heavy agent framework required.

2) High-level flow (one attempt)

Workspace prep (fresh snapshot):

Checkout the task’s base commit into a clean temp workspace.

Record dataset revision & base commit in a run manifest.

Context priming (we provide, no tool call needed):

Tree sketch: top ~300–500 file paths (.py, .txt, .cfg) with sizes.

Grep map: top keyword matches (from issue title / failing test names) with path:line:one-line snippet (capped).

(Optional, i2+): quick pytest -k to surface failing tests.

Interactive edit loop (tools only):

The model issues mini JSON commands inside fenced blocks (see §4).

Allowed tools (i1): LIST_TREE, GREP, READ, WRITE.

(Optional i2): add PYTEST_K for quick targeted tests.

Ready signal → we make the patch:

Model outputs READY_FOR_DIFF.

We run git add -A; then git diff --cached -U3 --no-color → this is the model_patch.

Run git apply --check on that diff for early validation:

If it fails, return the exact error string once; allow the model a final quick fix (within the same attempt time budget).

If it passes, we finalize.

Emit predictions line for this instance:

{"instance_id": "...", "model_name_or_path": "...", "model_patch": "<diff>"}


Evaluate with the official SWE-bench harness (unchanged).

3) Guardrails & budgets

No outbound network.

No step cap; only time caps:

Per-attempt wall-time (i1 default): 90 seconds. Increase only if evidence demands.

Per tool call (i1 default): 20–30 seconds.

CPU budget: ≤80% of 16 threads on your box.

Predictions concurrency: start at 8 model jobs; raise to 12 if stable.

Evaluator --max_workers: start at 4; raise to 6–8 once caches warm.

Fresh workspace per attempt. No cumulative drift.

4) Agent Interface Contract (AIC)
4.1 Protocol shape

The agent communicates tool invocations with fenced blocks:

Call block

```call
{"tool":"READ","path":"pandas/core/frame.py"}
```


Result block (our reply)

```result
{"ok":true,"content":"<first 1500 chars...>","truncated":true}
```


End-of-edits signal

READY_FOR_DIFF


The agent may interleave natural language reasoning between blocks, but all actions must be inside ```call blocks.

We respond only with ```result blocks (plus the final diff outcome). No extra narration.

4.2 Allowed tools (i1)

LIST_TREE
Input: {"tool":"LIST_TREE","limit":500}
Output: {"ok":true,"entries":[{"path":"...","bytes":1234,"ext":".py"}, ...], "truncated":false}

GREP
Input: {"tool":"GREP","pattern":"read_csv|to_parquet","glob":"**/*.py","max_hits":50}
Output: {"ok":true,"hits":[{"path":"pandas/io/parsers.py","line":123,"text":"...read_csv(...)"}, ...], "truncated":true}

READ
Input: {"tool":"READ","path":"pandas/core/frame.py","max_bytes":20000}
Output: {"ok":true,"content":"<file content>","truncated":false,"encoding":"utf-8"}

WRITE (atomic)
Input: {"tool":"WRITE","path":"pandas/core/frame.py","content":"<full new file>","encoding":"utf-8"}
Output: {"ok":true,"bytes":54321}

Note: WRITE always replaces the file with the provided content (atomic temp-file swap). Partial edits must be done by reading, modifying, and writing the full file content.

4.3 Optional tool (i2+)

PYTEST_K
Input: {"tool":"PYTEST_K","pattern":"test_to_parquet or test_read_csv","timeout_s":25}
Output: {"ok":true,"summary":{"passed":2,"failed":1,"xfailed":0,"skipped":0},"output":"short textual summary (capped)","timed_out":false}

4.4 Invalid calls

If input JSON is malformed or the path is outside the repo, we respond with {"ok":false,"error":"...reason..."}.

If a call exceeds per-command timeout, we return {"ok":false,"error":"timeout"}.

5) Prompts (templates)
5.1 System prompt (include once per attempt)

You are editing a local repository to resolve a failing SWE-bench instance.
Do not write patches. You will use tools to read and write files.
Tools available: LIST_TREE, GREP, READ, WRITE.
Protocol: issue commands inside fenced blocks labeled call containing a single JSON object.
After each call, wait for a result block before proceeding.
When all edits are complete, output exactly READY_FOR_DIFF on its own line.
Constraints: no network access; keep changes minimal; prefer targeted edits near failing behavior; preserve formatting and imports.

5.2 User prompt (per instance)

Task brief: the instance title/description and any failing test names if known.

Tree sketch: first ~300–500 files with sizes (we provide).

Grep map: top ~50 keyword hits with path:line:snippet (we provide).

Reminder: use the tools; do not output patches; end with READY_FOR_DIFF.

(These two prompts are sufficient for good coding models to operate zero-shot.)

6) Diff creation & validation (automated by harness)

On READY_FOR_DIFF:

git add -A

git diff --cached -U3 --no-color → model_patch

Sanity check: git apply --check against a fresh copy of the base tree.

If check fails once, return the exact error (patch failed: … or does not match index) to the agent; allow one quick fix (still within the attempt time box).

If check passes, finalize the predictions entry.

This reduces malformed patch rate essentially to zero and surfaces path/divergence issues before evaluator time is spent.

7) Workspace lifecycle & idempotence

Fresh start per attempt: new temp worktree / copy of the base repo.

Logging: keep a per-attempt log of tool calls (name, args hash, duration, bytes moved, exit code).

Crash-safe: if an attempt crashes, the orchestrator marks it and continues; finished (model, instance) pairs are skipped on rerun unless forced.

8) Metrics & acceptance gates (pre-evaluation)

Track these on a small i1 set (6–8 easy one-patch instances):

Malformed-patch rate (failed --check after one retry): < 5%

Path-not-found rate (READ/WRITE ENOENT): < 5%

Median attempt wall-time: ≤ 90 s

Best model > baseline (submit no-change patch) on the i1 set.

Do not run large sweeps or expand timeouts until these are green.

9) Concurrency & resource policy

CPU ceiling: ≤80% of 16 threads.

Predictions concurrency: start at 8; raise to 12 if system remains smooth (no provider rate limits).

Evaluator workers: start at 4; increase to 6–8 after caches warm and disk thrash is low.

10) Failure taxonomy & handling

provider_failed (HTTP/SDK/ratelimit): retry with backoff; if exhausted, mark cell and continue.

invalid_call (bad JSON / unknown tool): return error; let agent correct.

timeout_call: return timeout; agent may try an alternative.

apply_check_failed: send error once; allow one remediation write; if it still fails, finalize as malformed.

eval_error: evaluator crashed; capture stderr; continue with other cells.

skipped_unavailable_model: endpoint missing/renamed; record and continue.

11) Expansions by iteration

i1 (now): 4 tools, 90s/attempt, K=2, 6–8 easy one-patch tasks, 4–6 Chutes models.

i2: add PYTEST_K, multi-attempt (K=2 default, K=3 for harder ones), add OpenRouter models, leaderboard v1 (no token columns).

i3: 15–20 tasks including multi-patch & numpy/pandas; Shell-like editing remains; longer timeouts only where evidence demands; leaderboard v2.

i4: token & cost accounting + latency percentiles; leaderboard v3.

12) Security & privacy

No outbound network from the workspace.

Secrets (API keys) live in a gitignored credentials.txt (simple KEY=... lines).

Prompts/responses stored for reproducibility; redact keys/PII automatically.

13) Quick test plan (before running models)

Toy repo tests

WRITE a change in a single file → git diff shows correct patch → --check passes.

WRITE with missing final newline → patch still valid.

READ large file → truncated flag behaves; no crash.

Protocol robustness

Agent outputs a patch by mistake → harness ignores it (requires ```call blocks).

Bad JSON → returns invalid_call and recovers.

Performance sanity

8 parallel attempts keep CPU <80% and memory stable.

Logs include per-call durations and bytes; no unbounded growth.

14) FAQs

Q: Isn’t adding tools “more complex”?
A: No. The shim is tiny and replaces the hardest part (model-crafted diffs) with deterministic Git behavior.

Q: Why not just dump the whole repo to the model?
A: Token cost explodes and still doesn’t fix path accuracy. A tree sketch + grep map gives high-signal navigation at low cost.

Q: What if a task really needs running tests?
A: Add PYTEST_K in i2 for targeted checks, still capped at ~25–30s.

Q: Can we cap tool steps?
A: We don’t—time is the only budget. Good models often need a handful of calls; step caps create brittle failures.

15) Deliverables checklist (for the agent)

 Implement the micro-tools protocol (LIST_TREE, GREP, READ, WRITE; i2: PYTEST_K).

 Provide tree sketch and grep map at the start of each attempt.

 Honor READY_FOR_DIFF and generate model_patch via Git; run git apply --check.

 Enforce 90s/attempt (i1), 20–30s per call, fresh workspace per attempt.

 Log structured tool telemetry; capture prompts/responses (redacted).

 Meet acceptance gates: malformed-patch <5%, path-not-found <5%, best model > baseline.

 Keep CPU ≤80% (8→12 concurrent predictions; evaluator --max_workers 4→6–8).

 Produce predictions JSONL and run the official evaluator; archive artifacts.

Bottom line: Stop asking models to typeset diffs. Let them edit files with four tiny tools; let Git do the diffing. Your pass rate will start reflecting model ability, not environment friction.