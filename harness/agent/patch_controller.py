import re
from typing import Dict, List, Tuple


DIFF_FENCE_RE = re.compile(r"```(?:diff|patch)?\n(.*?)```", re.DOTALL)


def build_patch_system_prompt() -> str:
    return (
        "You are a highly skilled software engineer. "
        "Given a repository name and an issue description, you will propose a code fix as a unified diff. "
        "Output only the diff. No explanations. Ensure the patch applies cleanly using `git apply`."
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
    fields.append(
        "Instructions:\n"
        "- Produce a unified diff beginning with 'diff --git a/... b/...'.\n"
        "- Include only changed files and hunks.\n"
        "- Do not include analysis or commentary.\n"
    )
    return "\n\n".join(fields)


def extract_diff(text: str) -> str:
    # Try code-fenced block first
    m = DIFF_FENCE_RE.search(text)
    if m:
        candidate = m.group(1).strip()
        if looks_like_unified_diff(candidate):
            return candidate
    # Else, return the whole text if it looks like a diff
    if looks_like_unified_diff(text):
        return text.strip()
    # Fallback: empty (invalid)
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

