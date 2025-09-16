import re
from typing import Dict, List, Tuple
import os


DIFF_FENCE_RE = re.compile(r"```(?:diff|patch)?\n(.*?)```", re.DOTALL)
BEGIN_MARK = "BEGIN_PATCH"
END_MARK = "END_PATCH"


def build_patch_system_prompt() -> str:
    return (
        "You are a highly skilled software engineer. "
        "Given a repository name and an issue description, produce a SINGLE-FILE unified diff. "
        "Output STRICTLY between markers BEGIN_PATCH and END_PATCH. No commentary before or after. "
        "Ensure the patch applies cleanly with `git apply`."
    )


def build_patch_user_prompt(instance: Dict) -> str:
    fields = []
    iid = instance.get("instance_id")
    repo = instance.get("repo")
    title = instance.get("title") or instance.get("issue_title") or ""
    body = instance.get("problem_statement") or instance.get("issue_body") or ""
    fields.append(f"Instance: {iid}")
    if repo:
        fields.append(f"Repo: {repo}")
    if title:
        fields.append(f"Title: {title}")
    if body:
        fields.append("Issue:\n" + body.strip())
    # Repo path conventions (high-impact hints)
    repo = (instance.get("repo") or "").strip()
    repo_tips = {
        "pytest-dev/pytest": [
            "Source lives under src/ (e.g., src/_pytest/...)",
        ],
        "matplotlib/matplotlib": [
            "Library code under lib/ (e.g., lib/mpl_toolkits/..., NOT lib/matplotlib/...)",
        ],
        "pylint-dev/pylint": [
            "Library code under pylint/ (e.g., pylint/lint/pylinter.py)",
        ],
        "mwaskom/seaborn": [
            "Library code under seaborn/ (e.g., seaborn/_core/...)",
        ],
        "sympy/sympy": [
            "Library code under sympy/",
        ],
        "astropy/astropy": [
            "Library code under astropy/",
        ],
        "scikit-learn/scikit-learn": [
            "Library code under sklearn/",
        ],
    }
    if repo in repo_tips:
        fields.append("Repo path conventions:\n- " + "\n- ".join(repo_tips[repo]))

    # Try extracting file path hints from the issue text
    hints = extract_path_hints(instance)
    if hints:
        fields.append("Likely target file(s):\n- " + "\n- ".join(hints[:2]))
    fields.append(
        "Instructions:\n"
        "- Target a SINGLE FILE (choose the most likely).\n"
        "- Start with: diff --git a/<path> b/<path>\n"
        "- Then include '--- a/<path>' and '+++ b/<path>' lines.\n"
        "- Do NOT include multiple file diffs.\n"
        "- Do NOT use ellipses or placeholders; write full lines.\n"
        "- Ensure every line ends with a newline.\n"
        f"- Print ONLY the patch between lines '{BEGIN_MARK}' and '{END_MARK}'.\n"
    )
    fields.append(BEGIN_MARK)
    fields.append("<your unified diff here>")
    fields.append(END_MARK)
    return "\n\n".join(fields)


def extract_diff(text: str) -> str:
    if not isinstance(text, str):
        return ""
    s = text.strip()
    # Marker-based extraction has priority
    if BEGIN_MARK in s and END_MARK in s:
        s = s.split(BEGIN_MARK, 1)[1]
        s = s.split(END_MARK, 1)[0]
        s = s.strip()
        return s
    # Try code-fenced block
    m = DIFF_FENCE_RE.search(s)
    if m:
        candidate = m.group(1).strip()
        if looks_like_unified_diff(candidate):
            return candidate
    # Else, return the whole text if it looks like a diff
    if looks_like_unified_diff(s):
        return s
    # Fallback
    return ""


def looks_like_unified_diff(text: str) -> bool:
    # Heuristics: presence of diff headers and hunks
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    if any(ln.startswith("diff --git ") for ln in lines):
        return True
    if any(ln.startswith("@@ ") or ln.startswith("@@-") for ln in lines):
        return True
    if any(ln.startswith("--- ") for ln in lines) and any(ln.startswith("+++ ") for ln in lines):
        return True
    return False


def normalize_diff(text: str) -> str:
    """Normalize a unified diff to improve `git apply` success.

    - Remove code fences and marker lines if present
    - Keep only the first file's diff (drop additional files)
    - Ensure presence of ---/+++ after diff --git header if missing
    - Ensure trailing newline at end of patch
    """
    if not isinstance(text, str):
        return ""
    s = text.strip()
    # Remove code fences
    m = DIFF_FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()
    # Remove markers if present
    if BEGIN_MARK in s and END_MARK in s:
        s = s.split(BEGIN_MARK, 1)[1]
        s = s.split(END_MARK, 1)[0]
        s = s.strip()

    # Split by diff --git sections
    parts = []
    lines = s.splitlines()
    current: List[str] = []
    for ln in lines:
        if ln.startswith("diff --git "):
            if current:
                parts.append("\n".join(current))
                current = []
        current.append(ln)
    if current:
        parts.append("\n".join(current))

    if parts:
        s = parts[0]

    # Ensure --- / +++ present after diff header
    ls = s.splitlines()
    if ls and ls[0].startswith("diff --git "):
        hdr = ls[0]
        try:
            _, a, b = hdr.split(" ", 2)
            # a and b are like 'a/path' and 'b/path'
            a_path = a.split("a/", 1)[1] if "a/" in a else a
            b_path = b.split("b/", 1)[1] if "b/" in b else b
        except Exception:
            a_path = b_path = None
        has_minus = any(x.startswith("--- ") for x in ls[1:5])
        has_plus = any(x.startswith("+++ ") for x in ls[1:5])
        if (not has_minus or not has_plus) and a_path and b_path:
            # Insert after header
            rest = ls[1:]
            ins = [f"--- a/{a_path}", f"+++ b/{b_path}"]
            ls = [ls[0]] + ins + rest
        s = "\n".join(ls)

    # Ensure trailing newline
    if not s.endswith("\n"):
        s = s + "\n"
    return s


def rewrite_paths_for_repo(diff_text: str, repo: str) -> str:
    """Apply conservative path rewrites for known repo conventions.

    Only adjusts obvious, common mistakes in header paths.
    """
    if not isinstance(diff_text, str):
        return diff_text
    lines = diff_text.splitlines()
    def fix_path(p: str) -> str:
        # Normalize common mistakes
        if repo == "pytest-dev/pytest":
            # Insert src/ if missing for _pytest
            p = p.replace(" a/_pytest/", " a/src/_pytest/")
            p = p.replace(" b/_pytest/", " b/src/_pytest/")
        if repo == "matplotlib/matplotlib":
            # Only fix the mpl_toolkits subpackage path when mistakenly nested under lib/matplotlib/
            p = p.replace(" a/lib/matplotlib/mpl_toolkits/", " a/lib/mpl_toolkits/")
            p = p.replace(" b/lib/matplotlib/mpl_toolkits/", " b/lib/mpl_toolkits/")
        return p

    for i, ln in enumerate(lines):
        if ln.startswith("diff --git "):
            # Example: diff --git a/path b/path
            parts = ln.split()
            if len(parts) >= 4:
                a, b = parts[-2], parts[-1]
                new_a = fix_path(f" a/{a.split('a/',1)[1]}" if "a/" in a else f" {a}")
                new_b = fix_path(f" b/{b.split('b/',1)[1]}" if "b/" in b else f" {b}")
                lines[i] = "diff --git" + new_a + new_b
        elif ln.startswith("--- ") or ln.startswith("+++ "):
            # Fix ---/+++ lines similarly
            prefix, rest = ln[:4], ln[4:]
            if rest.startswith("a/"):
                ln_fixed = prefix + fix_path(" a/" + rest[2:])[1:]
            elif rest.startswith("b/"):
                ln_fixed = prefix + fix_path(" b/" + rest[2:])[1:]
            else:
                ln_fixed = ln
            lines[i] = ln_fixed
    out = "\n".join(lines)
    if not out.endswith("\n"):
        out += "\n"
    return out


def validate_diff_structure(text: str) -> (bool, str):
    """Lightweight structural validation for a unified diff.

    Checks:
    - has 'diff --git' header
    - has '--- ' and '+++ ' after header
    - has at least one '@@' hunk
    - within hunks, lines start with one of ' ', '+', '-' (and no other prefixes)
    """
    if not isinstance(text, str) or not text.strip():
        return False, "empty"
    lines = text.splitlines()
    if not any(ln.startswith("diff --git ") for ln in lines[:5]):
        return False, "missing diff header"
    # find first header
    try:
        idx = next(i for i, ln in enumerate(lines) if ln.startswith("diff --git "))
    except StopIteration:
        return False, "missing diff header"
    window = lines[idx + 1 : idx + 6]
    if not any(ln.startswith("--- ") for ln in window):
        return False, "missing --- line"
    if not any(ln.startswith("+++ ") for ln in window):
        return False, "missing +++ line"
    if not any("@@" in ln for ln in lines):
        return False, "missing hunk header"
    in_hunk = False
    for ln in lines:
        if ln.startswith("@@"):
            in_hunk = True
            continue
        if in_hunk:
            if ln and not (ln.startswith(" ") or ln.startswith("+") or ln.startswith("-")):
                # allow \ No newline at end of file
                if not ln.startswith("\\ No newline at end of file"):
                    return False, "invalid line prefix in hunk"
    return True, "ok"


def extract_path_hints(instance: Dict) -> List[str]:
    """Extract a few probable file paths from issue text.

    Heuristics:
    - Regex for path-like tokens ending with common extensions
    - Dotted module names -> convert to path.py
    - Filter to project-like paths (exclude URLs)
    """
    import re

    text = "\n".join(
        [
            str(instance.get("title") or instance.get("issue_title") or ""),
            str(instance.get("problem_statement") or instance.get("issue_body") or ""),
        ]
    )
    candidates: List[str] = []
    # Path patterns
    path_re = re.compile(r"(?:(?:\./)?[A-Za-z0-9_./-]+\.(?:py|rst|md|ini|cfg|yaml|yml|toml|txt))")
    for m in path_re.finditer(text):
        p = m.group(0)
        # Basic URL skip
        if p.startswith("http"):
            continue
        # Normalize leading './'
        if p.startswith("./"):
            p = p[2:]
        if p not in candidates:
            candidates.append(p)
    # Dotted module names followed by .py in text or error traces
    mod_re = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b")
    for m in mod_re.finditer(text):
        mod = m.group(1)
        if "." in mod:
            path = mod.replace(".", "/") + ".py"
            if path not in candidates:
                candidates.append(path)
    # Limit and return
    return candidates[:3]
