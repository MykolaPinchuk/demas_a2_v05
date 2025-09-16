import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple

from harness.providers.openai_compat import OpenAICompatChat, OpenAICompatError
from harness.preflight import ensure_repo


CALL_BLOCK_RE = re.compile(r"```call\n(\{[\s\S]*?\})\n```", re.MULTILINE)


def _safe_join(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    if not str(p).startswith(str(root.resolve())):
        raise ValueError("path escapes workspace")
    return p


def _list_tree(root: Path, limit: int = 500) -> Dict:
    entries = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip VCS
        if ".git" in dirnames:
            dirnames.remove(".git")
        for fn in filenames:
            fp = Path(dirpath) / fn
            try:
                st = fp.stat()
                size = st.st_size
            except OSError:
                size = 0
            ext = fp.suffix
            rel = fp.relative_to(root).as_posix()
            entries.append({"path": rel, "bytes": size, "ext": ext})
            count += 1
            if count >= limit:
                return {"ok": True, "entries": entries, "truncated": True}
    return {"ok": True, "entries": entries, "truncated": False}


def _grep(root: Path, pattern: str, glob: str = "**/*.py", max_hits: int = 50) -> Dict:
    import fnmatch
    import io

    try:
        rgx = re.compile(pattern)
    except re.error as e:
        return {"ok": False, "error": f"invalid regex: {e}"}
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for fn in filenames:
            rel = Path(dirpath).joinpath(fn).relative_to(root).as_posix()
            if not fnmatch.fnmatch(rel, glob):
                continue
            try:
                with open(root / rel, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if rgx.search(line):
                            hits.append({"path": rel, "line": i, "text": line.strip()[:240]})
                            if len(hits) >= max_hits:
                                return {"ok": True, "hits": hits, "truncated": True}
            except OSError:
                continue
    return {"ok": True, "hits": hits, "truncated": False}


def _read(root: Path, path: str, max_bytes: int = 20000) -> Dict:
    try:
        fp = _safe_join(root, path)
        data = Path(fp).read_bytes()
        content = data[:max_bytes].decode("utf-8", errors="replace")
        return {"ok": True, "content": content, "truncated": len(data) > max_bytes, "encoding": "utf-8"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _write(root: Path, path: str, content: str, encoding: str = "utf-8") -> Dict:
    try:
        fp = _safe_join(root, path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        tmp = fp.with_suffix(fp.suffix + ".tmp")
        tmp.write_text(content, encoding=encoding)
        os.replace(tmp, fp)
        return {"ok": True, "bytes": len(content.encode(encoding))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _init_git(root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=str(root), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-m", "base"], cwd=str(root), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _export_diff(root: Path) -> str:
    import subprocess

    subprocess.run(["git", "add", "-A"], cwd=str(root), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc = subprocess.run(["git", "diff", "--cached", "-U3", "--no-color"], cwd=str(root), capture_output=True, text=True)
    return proc.stdout


def _prepare_workspace(repo: str, commit: str | None) -> Path:
    cache = ensure_repo(repo)
    # checkout specific commit into cache (best-effort)
    if commit:
        import subprocess

        subprocess.run(["git", "-C", str(cache), "fetch", "--depth", "1", "origin", commit], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "-C", str(cache), "checkout", commit], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = Path(tempfile.mkdtemp(prefix="ws_"))
    # copy snapshot without .git
    shutil.copytree(cache, ws, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
    _init_git(ws)
    return ws


def run_edit_attempt(
    client: OpenAICompatChat,
    instance: Dict,
    temperature: float,
    max_output_tokens: int,
    seed: int,
    per_call_cap: float = 25.0,
    wall_time_cap: float = 90.0,
    max_calls: int = 12,
) -> Tuple[str, Dict]:
    """Runs a single editing attempt. Returns (diff, meta). diff may be ''.
    """
    start = time.time()
    repo = instance.get("repo") or ""
    commit = instance.get("base_commit")
    ws = _prepare_workspace(repo, commit)

    sys_prompt = (
        "You are editing a local repository to resolve a SWE-bench instance.\n"
        "Do not write patches. Use tools to read and write files.\n"
        "Tools: LIST_TREE, GREP, READ, WRITE.\n"
        "Protocol: issue commands inside fenced blocks labeled call containing JSON.\n"
        "After each call, wait for a result block. When done, output exactly READY_FOR_DIFF.\n"
        "Constraints: no network; keep changes minimal; prefer targeted edits; preserve formatting.\n\n"
        "Example call/result:\n"
        "```call\n{\"tool\":\"LIST_TREE\",\"limit\":30}\n```\n"
        "```result\n{\"ok\":true,\"entries\":[{\"path\":\"src/_pytest/assertion/rewrite.py\",\"bytes\":1234,\"ext\":\".py\"}],\"truncated\":true}\n```\n"
        "Continue issuing call blocks until you are done, then output READY_FOR_DIFF.\n"
    )
    # Provide a small initial tree sketch to orient the model
    tree = _list_tree(ws, limit=300)
    grep_seed = []  # We can add keyword-derived hints later if needed
    user_prompt = (
        f"Instance: {instance.get('instance_id')}\nRepo: {repo}\n\n"
        f"Task:\n{instance.get('problem_statement') or ''}\n\n"
        "Tree sketch (first ~300 files):\n"
        + "\n".join(f"- {e['path']} ({e['bytes']} bytes)" for e in tree.get("entries", [])[:50])
        + "\n\nUse the tools; do not output patches; end with READY_FOR_DIFF."
    )

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]

    calls = 0
    meta = {"calls": 0}
    while time.time() - start < wall_time_cap and calls < max_calls:
        try:
            text, usage = client.chat(messages, temperature=temperature, max_output_tokens=max_output_tokens, seed=seed)
            meta.update({
                "prompt_tokens": meta.get("prompt_tokens", 0) + usage.get("prompt_tokens", 0),
                "completion_tokens": meta.get("completion_tokens", 0) + usage.get("completion_tokens", 0),
                "total_tokens": meta.get("total_tokens", 0) + usage.get("total_tokens", 0),
            })
        except OpenAICompatError as e:
            return "", {"error": str(e)}

        if "READY_FOR_DIFF" in text:
            # Export diff and return
            diff = _export_diff(ws)
            return diff, meta

        m = CALL_BLOCK_RE.search(text)
        if not m:
            # Ask the model to use tools explicitly
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "```result\n{\"ok\":false,\"error\":\"No call block found. Use LIST_TREE/GREP/READ/WRITE and end with READY_FOR_DIFF.\"}\n```"})
            continue
        calls += 1
        meta["calls"] = calls
        try:
            payload = json.loads(m.group(1))
        except Exception as e:
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": f"```result\n{{\"ok\":false,\"error\":\"invalid JSON: {str(e)}\"}}\n```"})
            continue

        tool = payload.get("tool")
        result = {"ok": False, "error": "unknown tool"}
        t0 = time.time()
        try:
            if tool == "LIST_TREE":
                result = _list_tree(ws, int(payload.get("limit", 500)))
            elif tool == "GREP":
                result = _grep(ws, str(payload.get("pattern", ".")), str(payload.get("glob", "**/*.py")), int(payload.get("max_hits", 50)))
            elif tool == "READ":
                result = _read(ws, str(payload.get("path", "")), int(payload.get("max_bytes", 20000)))
            elif tool == "WRITE":
                result = _write(ws, str(payload.get("path", "")), str(payload.get("content", "")), str(payload.get("encoding", "utf-8")))
        except Exception as e:
            result = {"ok": False, "error": str(e)}
        dt = time.time() - t0
        result["duration_s"] = round(dt, 3)
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": f"```result\n{json.dumps(result)}\n```"})

    # Budget exceeded
    diff = _export_diff(ws)
    return diff, meta
