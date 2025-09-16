import os, json
from datasets import load_dataset


def select_easy(ds, max_lines=120, max_hunks=6, max_files=1):
    sel = []
    for rec in ds:
        iid = rec.get('instance_id')
        patch = rec.get('patch') or rec.get('patches') or rec.get('gold_patch') or ''
        if isinstance(patch, list):
            patch_text = '\n'.join(str(p) for p in patch)
        else:
            patch_text = str(patch)
        lines = patch_text.splitlines()
        n_lines = len(lines)
        n_add = sum(1 for x in lines if x.startswith('+'))
        n_del = sum(1 for x in lines if x.startswith('-'))
        n_hunks = sum(1 for x in lines if x.startswith('@@'))
        n_files = len([x for x in lines if x.startswith('diff --git ')])
        if n_files == 0:
            n_files = len([x for x in lines if x.startswith('+++ ')])
        if n_lines and n_lines <= max_lines and n_hunks <= max_hunks and (n_files == 0 or n_files <= max_files):
            sel.append({'instance_id': iid, 'repo': rec.get('repo',''), 'n_lines': n_lines, 'n_hunks': n_hunks, 'n_files': n_files, 'n_add': n_add, 'n_del': n_del})
    # sort easiest first
    sel.sort(key=lambda x: (x['n_files'], x['n_hunks'], x['n_lines']))
    return sel


def main():
    ds = load_dataset('princeton-nlp/SWE-bench_Lite', split='test')
    seed = int(os.getenv('SELECTION_SEED', '42'))
    # Primary pass: strict(ish)
    sel = select_easy(ds, max_lines=120, max_hunks=6, max_files=1)
    # Backfill passes until we get 8
    if len(sel) < 8:
        pool = select_easy(ds, max_lines=160, max_hunks=6, max_files=1)
        ids = {x['instance_id'] for x in sel}
        for x in pool:
            if x['instance_id'] not in ids:
                sel.append(x)
                ids.add(x['instance_id'])
            if len(sel) >= 8:
                break
    if len(sel) < 8:
        pool = select_easy(ds, max_lines=200, max_hunks=8, max_files=2)
        ids = {x['instance_id'] for x in sel}
        for x in pool:
            if x['instance_id'] not in ids:
                sel.append(x)
                ids.add(x['instance_id'])
            if len(sel) >= 8:
                break

    out_dir = 'instances'
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'i1_instances_lite_easy.jsonl')
    with open(out_path, 'w') as f:
        for x in sel[:8]:
            f.write(json.dumps({'instance_id': x['instance_id']}) + '\n')
    manifest = {
        'dataset_name': 'princeton-nlp/SWE-bench_Lite/test',
        'selection_seed': seed,
        'filters_primary': {'max_lines': 120, 'max_hunks': 6, 'max_files': 1},
        'filters_backfill_1': {'max_lines': 160, 'max_hunks': 6, 'max_files': 1},
        'filters_backfill_2': {'max_lines': 200, 'max_hunks': 8, 'max_files': 2},
        'selected_preview': sel[:8],
    }
    with open(os.path.join(out_dir, 'i1_instances_manifest_easy.json'), 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"Pinned {min(8, len(sel))} easy instances to {out_path}")
    for x in sel[:8]:
        print(json.dumps(x))


if __name__ == '__main__':
    main()

