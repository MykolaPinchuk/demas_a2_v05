import os
from pathlib import Path


def load_credentials_into_env(path: str = "credentials.txt") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and v and k not in os.environ:
            os.environ[k] = v


def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def get_workers_default() -> int:
    return env_int("WORKERS", 12)


def get_eval_workers_default() -> int:
    return env_int("EVAL_WORKERS", 4)


def get_dataset_name_default() -> str:
    return os.getenv("DATASET_NAME", "princeton-nlp/SWE-bench_Lite")


def get_selection_seed_default() -> int:
    return env_int("SELECTION_SEED", 42)


def chutes_base_url_default() -> str:
    # OpenAI-compatible default; override via CHUTES_BASE_URL
    # Chutes chat endpoint (host confirmed working):
    return os.getenv("CHUTES_BASE_URL", "https://llm.chutes.ai/v1/chat/completions")


def openrouter_base_url_default() -> str:
    return os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
