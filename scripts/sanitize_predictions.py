#!/usr/bin/env python3
import argparse, json, re, sys

DIFF_FENCE_RE = re.compile(r"```(?:diff|patch)?\n(.*?)```", re.DOTALL)
BEGIN_MARK = "BEGIN_PATCH"
END_MARK = "END_PATCH"

def sanitize_patch(p: str) -> str:
    if not isinstance(p, str):
        return ""
    s = p.strip()
    m = DIFF_FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()
    # Remove markers if present
    if BEGIN_MARK in s and END_MARK in s:
        s = s.split(BEGIN_MARK, 1)[1]
        s = s.split(END_MARK, 1)[0]
        s = s.strip()
    # Strip lone trailing code fence if present
    if s.endswith("```"):
        s = s[: -3].rstrip()
    # Drop standalone marker lines if they leaked
    lines = [ln for ln in s.splitlines() if ln.strip() not in (BEGIN_MARK, END_MARK)]
    s = "\n".join(lines)
    return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Path to predictions.jsonl")
    ap.add_argument("-o", "--output", help="Output path", default=None)
    args = ap.parse_args()

    out = args.output or (args.input.rsplit(".", 1)[0] + ".sanitized.jsonl")
    changed = 0
    total = 0
    with open(args.input, 'r') as fin, open(out, 'w') as fout:
        for ln in fin:
            if not ln.strip():
                continue
            obj = json.loads(ln)
            total += 1
            orig = obj.get('model_patch', '')
            sani = sanitize_patch(orig)
            if sani != orig:
                changed += 1
            obj['model_patch'] = sani
            fout.write(json.dumps(obj) + '\n')
    print(f"Wrote {out} (sanitized {changed}/{total})")

if __name__ == '__main__':
    main()
