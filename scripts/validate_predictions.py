#!/usr/bin/env python3
import argparse, json, sys
from harness.agent.patch_controller import looks_like_unified_diff

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("predictions", help="Path to predictions.jsonl")
    args = ap.parse_args()

    ok = True
    with open(args.predictions, 'r') as f:
        for i, ln in enumerate(f, 1):
            try:
                obj = json.loads(ln)
            except Exception as e:
                print(f"Line {i}: invalid JSON: {e}")
                ok = False
                continue
            for key in ["instance_id", "model_name_or_path", "model_patch"]:
                if key not in obj:
                    print(f"Line {i}: missing field '{key}'")
                    ok = False
            patch = obj.get("model_patch", "")
            if patch and not looks_like_unified_diff(patch):
                print(f"Line {i}: model_patch does not look like a unified diff")
                ok = False
    if ok:
        print("Predictions file looks well-formed.")
        sys.exit(0)
    else:
        print("Issues found in predictions.")
        sys.exit(1)

if __name__ == '__main__':
    main()

