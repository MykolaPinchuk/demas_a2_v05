import os, json
from datasets import load_dataset

PREFERRED_REPOS = [
    "pytest-dev/pytest",
    "mwaskom/seaborn",
    "astropy/astropy",
    "matplotlib/matplotlib",
    "sympy/sympy",
    "pandas-dev/pandas",
    "numpy/numpy",
    "scikit-learn/scikit-learn",
    "pylint-dev/pylint",
    "scipy/scipy",
]


def metrics_from_patch_text(patch_text: str):
    lines = patch_text.splitlines()
    n_lines = len(lines)
    n_add = sum(1 for x in lines if x.startswith('+'))
    n_del = sum(1 for x in lines if x.startswith('-'))
    n_hunks = sum(1 for x in lines if x.startswith('@@'))
    n_files = len([x for x in lines if x.startswith('diff --git ')])
    if n_files == 0:
        n_files = len([x for x in lines if x.startswith('+++ ')])
    return n_lines, n_add, n_del, n_hunks, n_files


def main():
    ds = load_dataset('princeton-nlp/SWE-bench_Lite', split='test')
    # Build candidates, excluding Django (per user request)
    cand_by_repo = {}
    for rec in ds:
        repo = rec.get('repo') or ''
        if repo == 'django/django':
            continue
        patch = rec.get('patch') or rec.get('patches') or rec.get('gold_patch') or ''
        if isinstance(patch, list):
            patch_text = '\n'.join(str(p) for p in patch)
        else:
            patch_text = str(patch)
        n_lines, n_add, n_del, n_hunks, n_files = metrics_from_patch_text(patch_text)
        if not n_lines:
            continue
        if n_lines <= 120 and n_hunks <= 6 and (n_files == 0 or n_files <= 1):
            item = {
                'instance_id': rec.get('instance_id'),
                'repo': repo,
                'n_lines': n_lines,
                'n_hunks': n_hunks,
                'n_files': n_files,
                'n_add': n_add,
                'n_del': n_del,
            }
            cand_by_repo.setdefault(repo, []).append(item)
    # Sort each repo's items by ease
    for repo, arr in cand_by_repo.items():
        arr.sort(key=lambda x: (x['n_files'], x['n_hunks'], x['n_lines']))

    # First pass: take easiest from preferred repos in order
    final = []
    seen_ids = set()
    for repo in PREFERRED_REPOS:
        if repo in cand_by_repo and cand_by_repo[repo]:
            pick = cand_by_repo[repo][0]
            if pick['instance_id'] not in seen_ids:
                final.append(pick)
                seen_ids.add(pick['instance_id'])
            if len(final) >= 8:
                break

    # Second pass: fill remaining with easiest across other repos (excluding Django)
    if len(final) < 8:
        pool = []
        for repo, arr in cand_by_repo.items():
            if repo in PREFERRED_REPOS:
                # also consider second best etc.
                pool.extend(arr[1:])
            else:
                pool.extend(arr)
        pool.sort(key=lambda x: (x['n_files'], x['n_hunks'], x['n_lines']))
        for it in pool:
            if it['instance_id'] in seen_ids:
                continue
            final.append(it)
            seen_ids.add(it['instance_id'])
            if len(final) >= 8:
                break

    out_dir = 'instances'
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'i1_instances_lite_easy_diverse.jsonl')
    with open(out_path, 'w') as f:
        for x in final[:8]:
            f.write(json.dumps({'instance_id': x['instance_id']}) + '\n')
    manifest = {
        'dataset_name': 'princeton-nlp/SWE-bench_Lite/test',
        'policy': 'easy + diverse by repo; exclude django/django',
        'filters': {'max_lines': 120, 'max_hunks': 6, 'max_files': 1},
        'preferred_repos': PREFERRED_REPOS,
        'selected_preview': final[:8],
    }
    with open(os.path.join(out_dir, 'i1_instances_manifest_easy_diverse.json'), 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"Pinned {min(8, len(final))} diverse easy instances to {out_path}")
    for x in final[:8]:
        print(json.dumps(x))


if __name__ == '__main__':
    main()

