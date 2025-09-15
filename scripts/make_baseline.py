import argparse, json, os, time

def load_instances(path):
    ids = []
    with open(path, 'r') as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            obj = json.loads(ln)
            iid = obj.get('instance_id')
            if iid:
                ids.append(iid)
    return ids

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--instances', default='instances/i1_instances_lite.jsonl')
    ap.add_argument('--run_id', default=f"baseline-{int(time.time())}")
    ap.add_argument('--model_name', default='baseline_no_patch')
    args = ap.parse_args()

    instance_ids = load_instances(args.instances)
    run_dir = os.path.join('runs', args.run_id)
    os.makedirs(run_dir, exist_ok=True)

    pred_path = os.path.join(run_dir, 'predictions.jsonl')
    with open(pred_path, 'w') as f:
        for iid in instance_ids:
            row = {
                'instance_id': iid,
                'model_name_or_path': args.model_name,
                # Provide both keys for compatibility
                'model_patch': '',
                'patch': '',
            }
            f.write(json.dumps(row) + '\n')

    manifest = {
        'run_id': args.run_id,
        'generated': int(time.time()),
        'instances_path': os.path.abspath(args.instances),
        'predictions_path': os.path.abspath(pred_path),
        'model_name_or_path': args.model_name,
        'note': 'Baseline run with empty patches for all instances.'
    }
    with open(os.path.join(run_dir, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"Baseline predictions written to {pred_path}")
    print(f"Manifest written to {os.path.join(run_dir, 'manifest.json')}")

if __name__ == '__main__':
    main()

