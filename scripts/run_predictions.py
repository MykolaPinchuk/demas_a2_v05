#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import yaml

from harness.config import load_credentials_into_env
from harness.orchestrator import orchestrate_predictions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_id", required=True)
    ap.add_argument("--instances", default="instances/i1_instances_lite.jsonl")
    ap.add_argument("--models_config", default="config/models_i1.yaml")
    ap.add_argument("--attempts", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max_output_tokens", type=int, default=2000)
    ap.add_argument("--mode", choices=["patch","edit"], default="patch")
    args = ap.parse_args()

    load_credentials_into_env()
    cfg = yaml.safe_load(Path(args.models_config).read_text())
    model_specs = cfg.get("models", [])
    pred_path = orchestrate_predictions(
        run_id=args.run_id,
        instances_path=args.instances,
        model_specs=model_specs,
        attempts=args.attempts,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
        mode=args.mode,
    )
    print(f"Predictions written: {pred_path}")


if __name__ == "__main__":
    main()
