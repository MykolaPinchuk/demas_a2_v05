import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, Optional


CACHE_DIR = Path(".cache/repos")


def ensure_repo(repo: str, timeout: int = 30) -> Path:
    """Clone or refresh a shallow copy of the repo under .cache/repos/<owner>/<name>.

    We use default branch head; this is advisory (path existence), not exact commit.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    owner_name = repo.strip()
    dest = CACHE_DIR / owner_name
    url = f"https://github.com/{owner_name}.git"
    if dest.exists() and (dest / ".git").exists():
        # refresh
        try:
            subprocess.run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
            subprocess.run(["git", "-C", str(dest), "reset", "--hard", "origin/HEAD"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
    else:
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=False, timeout=timeout,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dest


def preflight_apply(repo: str, patch_text: str, commit: Optional[str] = None, timeout: int = 15) -> Tuple[bool, str]:
    """Run `git apply --check` on the patch against a shallow repo clone.

    Returns (ok, stderr_text). This is advisory to catch path/format issues.
    """
    try:
        repo_dir = ensure_repo(repo)
    except Exception as e:
        return False, f"preflight: repo setup failed: {e}"

    # Clean workspace and reset
    try:
        subprocess.run(["git", "-C", str(repo_dir), "clean", "-fdx"], check=False, timeout=timeout,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "-C", str(repo_dir), "checkout", "."], check=False, timeout=timeout,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if commit:
            # fetch and checkout specific commit
            subprocess.run(["git", "-C", str(repo_dir), "fetch", "--depth", "1", "origin", commit],
                           check=False, timeout=timeout,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "-C", str(repo_dir), "checkout", commit], check=False, timeout=timeout,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        pass

    # Write patch to temp file
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write(patch_text)
        tf.flush()
        patch_path = tf.name

    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), "apply", "--check", "--ignore-space-change", "--ignore-whitespace", patch_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
        )
        ok = proc.returncode == 0
        err = proc.stderr.strip()
        return ok, err
    except subprocess.TimeoutExpired:
        return False, "preflight: git apply --check timed out"
    finally:
        try:
            os.unlink(patch_path)
        except OSError:
            pass


def repo_file_hints(repo: str, keywords: Tuple[str, ...], limit: int = 5, timeout: int = 10):
    """Return up to `limit` repo paths that contain the given keywords in their path.

    Keywords are matched case-insensitively on path segments; only Python and text-like
    files are considered.
    """
    repo_dir = ensure_repo(repo, timeout=timeout)
    try:
        proc = subprocess.run(["git", "-C", str(repo_dir), "ls-files"], capture_output=True, text=True, timeout=timeout)
        files = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    except subprocess.TimeoutExpired:
        files = []
    if not files:
        return []
    keys = [k.lower() for k in keywords if len(k) >= 3]
    def score(path: str) -> int:
        p = path.lower()
        return sum(1 for k in keys if k in p)
    exts = (".py", ".pyi", ".rst", ".md", ".ini", ".cfg", ".yaml", ".yml", ".toml")
    cand = [f for f in files if f.endswith(exts)]
    cand.sort(key=lambda p: (-score(p), len(p)))
    out = []
    for p in cand:
        if score(p) <= 0:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out
