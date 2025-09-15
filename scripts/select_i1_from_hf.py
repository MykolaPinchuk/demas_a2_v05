import os, json
from datasets import load_dataset

def main():
    ds = load_dataset('princeton-nlp/SWE-bench_Lite', split='test')
    # Heuristics
    sel = []
    for rec in ds:
        iid = rec.get('instance_id') or rec.get('id') or rec.get('instanceID')
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
        if n_lines and n_lines <= 120 and n_hunks <= 6 and (n_files == 0 or n_files <= 2):
            sel.append({'instance_id': iid, 'repo': rec.get('repo', ''), 'n_lines': n_lines, 'n_hunks': n_hunks, 'n_files': n_files, 'n_add': n_add, 'n_del': n_del})
    sel.sort(key=lambda x: (x['n_files'], x['n_hunks'], x['n_lines']))
    final = []
    seen_repos = set()
    for obj in sel:
        if obj['repo'] and obj['repo'] not in seen_repos:
            final.append(obj)
            seen_repos.add(obj['repo'])
        if len(final) >= 6:
            break
    if len(final) < 6:
        have = {x['instance_id'] for x in final}
        for obj in sel:
            if obj['instance_id'] in have:
                continue
            final.append(obj)
            if len(final) >= 8:
                break
    os.makedirs('instances', exist_ok=True)
    with open('instances/i1_instances_lite.jsonl', 'w') as f:
        for obj in final:
            f.write(json.dumps({'instance_id': obj['instance_id']}) + '\n')
    manifest = {
        'dataset_name': 'princeton-nlp/SWE-bench_Lite/test',
        'selection_seed': int(os.getenv('SELECTION_SEED', '42')),
        'filters': {'max_lines': 120, 'max_hunks': 6, 'max_files': 2},
        'selected_count': len(final),
        'notes': 'Heuristics favor small diffs and few hunks/files; preference for diverse repos.',
    }
    with open('instances/i1_instances_manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"Pinned {len(final)} instances to instances/i1_instances_lite.jsonl from {manifest['dataset_name']}")
    for obj in final:
        print(json.dumps(obj))

if __name__ == '__main__':
    main()

