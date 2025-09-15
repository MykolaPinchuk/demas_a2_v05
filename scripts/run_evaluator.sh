#!/usr/bin/env bash
set -euo pipefail

PREDICTIONS_PATH="${1:-runs/baseline/predictions.jsonl}"
RUN_ID="${2:-baseline}"
DATASET_NAME="${DATASET_NAME:-princeton-nlp/SWE-bench_Lite}"
EVAL_WORKERS="${EVAL_WORKERS:-4}"

echo "Dataset: $DATASET_NAME"
echo "Predictions: $PREDICTIONS_PATH"
echo "Run ID: $RUN_ID"
echo "Workers: $EVAL_WORKERS"

# Note: Requires SWE-bench evaluator installed and Docker configured.
python -m swebench.harness.run_evaluation \
  --dataset_name "$DATASET_NAME" \
  --predictions_path "$PREDICTIONS_PATH" \
  --max_workers "$EVAL_WORKERS" \
  --run_id "$RUN_ID"

