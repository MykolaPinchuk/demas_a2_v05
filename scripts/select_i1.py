import json, sys, os, urllib.request

URLS = [
    'https://raw.githubusercontent.com/princeton-nlp/SWE-bench/main/swebench/selection/lite/swebench_lite.jsonl',
    'https://raw.githubusercontent.com/princeton-nlp/SWE-bench/main/swebench/selection/lite/lite_instances.jsonl',
    'https://raw.githubusercontent.com/princeton-nlp/SWE-bench/main/swebench/selection/lite/lite.jsonl',
    'https://huggingface.co/datasets/princeton-nlp/SWE-bench/resolve/main/selection/lite/swebench_lite.jsonl',
]

def fetch_lite():
    last_err = None
    for u in URLS:
        try:
            with urllib.request.urlopen(u, timeout=20) as r:
                txt = r.read().decode('utf-8')
                return u, [json.loads(ln) for ln in txt.splitlines() if ln.strip()]
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Unable to fetch SWE-bench Lite: {last_err}")

def main():
    src, instances = fetch_lite()
    sel = []
    for obj in instances:
        iid = obj.get('instance_id') or obj.get('id') or obj.get('instanceID')
        patch = obj.get('patch') or obj.get('patches') or obj.get('gold_patch') or ''
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
            sel.append({'instance_id': iid, 'n_lines': n_lines, 'n_hunks': n_hunks, 'n_files': n_files, 'n_add': n_add, 'n_del': n_del})
    sel.sort(key=lambda x: (x['n_files'], x['n_hunks'], x['n_lines']))
    final = []
    seen_repos = set()
    for obj in sel:
        iid = obj['instance_id']
        rec = next((r for r in instances if (r.get('instance_id') or r.get('id') or r.get('instanceID')) == iid), None)
        repo = (rec or {}).get('repo') or (rec or {}).get('repo_name') or ''
        if repo and repo not in seen_repos:
            final.append((iid, repo, obj))
            seen_repos.add(repo)
        if len(final) >= 6:
            break
    if len(final) < 6:
        have = {iid for iid,_,_ in final}
        for obj in sel:
            iid = obj['instance_id']
            if iid in have:
                continue
            rec = next((r for r in instances if (r.get('instance_id') or r.get('id') or r.get('instanceID')) == iid), None)
            repo = (rec or {}).get('repo') or (rec or {}).get('repo_name') or ''
            final.append((iid, repo, obj))
            if len(final) >= 8:
                break
    os.makedirs('instances', exist_ok=True)
    with open('instances/i1_instances_lite.jsonl', 'w') as f:
        for iid, repo, obj in final:
            f.write(json.dumps({'instance_id': iid}) + '\n')
    manifest = {
        'dataset_source': src,
        'selection_seed': int(os.getenv('SELECTION_SEED', '42')),
        'filters': {'max_lines': 120, 'max_hunks': 6, 'max_files': 2},
        'selected_count': len(final),
        'notes': 'Heuristics favor small diffs and few hunks/files; preference for diverse repos.',
    }
    with open('instances/i1_instances_manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"Pinned {len(final)} instances to instances/i1_instances_lite.jsonl from {src}")
    for iid, repo, obj in final:
        print(json.dumps({'instance_id': iid, 'repo': repo, **obj}))

if __name__ == '__main__':
    main()

