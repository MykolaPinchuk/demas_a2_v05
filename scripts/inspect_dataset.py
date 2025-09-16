#!/usr/bin/env python3
from datasets import load_dataset
import json
import sys

def main():
    name = sys.argv[1] if len(sys.argv) > 1 else 'princeton-nlp/SWE-bench_Lite'
    split = sys.argv[2] if len(sys.argv) > 2 else 'test'
    ds = load_dataset(name, split=split)
    print('num_rows', len(ds))
    rec = ds[0]
    print('keys', list(rec.keys()))
    fields = {k: rec.get(k) for k in ('instance_id','repo','base_commit','version','title','problem_statement','gold_patch','patch','test_patch') if k in rec}
    print(json.dumps(fields, indent=2)[:2000])

if __name__ == '__main__':
    main()

