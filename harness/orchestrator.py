import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from harness.config import (
    load_credentials_into_env,
    get_workers_default,
)
from harness.providers.openai_compat import OpenAICompatChat, OpenAICompatError
from harness.agent.patch_controller import (
    build_patch_system_prompt,
    build_patch_user_prompt,
    extract_diff,
)


def load_instances_jsonl(path: str) -> List[str]:
    ids: List[str] = []
    with open(path, "r") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            obj = json.loads(ln)
            iid = obj.get("instance_id")
            if iid:
                ids.append(iid)
    return ids


def load_dataset_records(instance_ids: Iterable[str]) -> Dict[str, Dict]:
    # Load from HF to build prompts (title/body/repo info).
    try:
        from datasets import load_dataset
    except Exception as e:
        raise RuntimeError("Please install `datasets` package")
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    by_id: Dict[str, Dict] = {}
    wanted = set(instance_ids)
    for rec in ds:
        iid = rec.get("instance_id")
        if iid in wanted:
            by_id[iid] = rec
    missing = wanted - set(by_id.keys())
    if missing:
        raise RuntimeError(f"Missing instances in dataset: {sorted(missing)}")
    return by_id


def make_client(provider: str, model: str) -> OpenAICompatChat:
    provider = provider.lower()
    if provider == "chutes":
        base_url = os.getenv("CHUTES_BASE_URL", "https://llm.chutes.ai/v1/chat/completions")
        api_key = os.getenv("CHUTES_API_KEY", "")
        if not api_key:
            raise RuntimeError("CHUTES_API_KEY not set; put it in credentials.txt or env")
        return OpenAICompatChat(base_url=base_url, api_key=api_key, model=model)
    elif provider == "openrouter":
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set; put it in credentials.txt or env")
        extra = {"HTTP-Referer": "https://example.com", "X-Title": "SWE-bench Harness"}
        return OpenAICompatChat(base_url=base_url, api_key=api_key, model=model, extra_headers=extra)
    else:
        raise RuntimeError(f"Unknown provider: {provider}")


def run_patch_attempt(
    client: OpenAICompatChat,
    instance: Dict,
    temperature: float,
    max_output_tokens: int,
    seed: int,
) -> Tuple[str, Dict]:
    sys_prompt = build_patch_system_prompt()
    user = build_patch_user_prompt(instance)
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}]
    try:
        text, meta = client.chat(messages, temperature=temperature, max_output_tokens=max_output_tokens, seed=seed)
    except OpenAICompatError as e:
        return "", {"error": str(e)}
    diff = extract_diff(text)
    if not diff:
        # Try a corrective nudge within the same attempt
        messages.append({"role": "assistant", "content": text})
        messages.append(
            {
                "role": "user",
                "content": "Your previous output was not a unified diff. Reply again with ONLY a valid unified diff (no commentary).",
            }
        )
        try:
            text2, meta2 = client.chat(
                messages, temperature=temperature, max_output_tokens=max_output_tokens, seed=seed
            )
            meta.update({k: meta.get(k, 0) + meta2.get(k, 0) for k in ["prompt_tokens", "completion_tokens", "total_tokens"]})
            diff = extract_diff(text2)
        except OpenAICompatError as e:
            return "", {"error": str(e), **meta}
    return diff, meta


def orchestrate_predictions(
    run_id: str,
    instances_path: str,
    model_specs: List[Dict],
    attempts: int = 2,
    temperature: float = 0.2,
    max_output_tokens: int = 2000,
) -> str:
    load_credentials_into_env()

    out_dir = Path("runs") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_path = out_dir / "predictions.jsonl"
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    instance_ids = load_instances_jsonl(instances_path)
    by_id = load_dataset_records(instance_ids)

    workers = get_workers_default()
    attempts_log = out_dir / "logs" / "attempts.jsonl"
    with ThreadPoolExecutor(max_workers=workers) as ex, open(pred_path, "w") as outf:
        futures = []
        for spec in model_specs:
            provider = spec["provider"]
            model_name = spec["model"]
            seed = int(spec.get("seed", 42))
            client = make_client(provider, model_name)
            for iid in instance_ids:
                instance = by_id[iid]
                futures.append(
                    ex.submit(
                        _per_instance,
                        outf.name,
                        str(attempts_log),
                        provider,
                        model_name,
                        client,
                        iid,
                        instance,
                        attempts,
                        temperature,
                        max_output_tokens,
                        seed,
                    )
                )
        for fut in as_completed(futures):
            fut.result()

    # write manifest
    manifest = {
        "run_id": run_id,
        "instances_path": os.path.abspath(instances_path),
        "predictions_path": str(pred_path.resolve()),
        "models": model_specs,
        "attempts": attempts,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "generated": int(time.time()),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return str(pred_path)


def _write_line(path: str, row: Dict) -> None:
    # serialize atomically per line append
    line = json.dumps(row) + "\n"
    with open(path, "a") as f:
        f.write(line)


def _per_instance(
    pred_path: str,
    attempts_log_path: str,
    provider: str,
    model_name: str,
    client: OpenAICompatChat,
    iid: str,
    instance: Dict,
    attempts: int,
    temperature: float,
    max_output_tokens: int,
    seed: int,
) -> None:
    last_patch = ""
    last_meta: Dict = {}
    status = "failed"
    for k in range(attempts):
        attempt_seed = seed + k
        patch, meta = run_patch_attempt(client, instance, temperature, max_output_tokens, attempt_seed)
        if patch:
            last_patch = patch
            last_meta = meta
            status = "ok"
            _log_attempt(attempts_log_path, iid, provider, model_name, k, attempt_seed, status, meta)
            break
        else:
            last_meta = meta
            status = "no_valid_patch"
            _log_attempt(attempts_log_path, iid, provider, model_name, k, attempt_seed, status, meta)

    row = {
        "instance_id": iid,
        "model_name_or_path": f"{provider}:{model_name}",
        "model_patch": last_patch,
        "status": status,
        "usage": last_meta,
    }
    _write_line(pred_path, row)


def _log_attempt(
    attempts_log_path: str,
    iid: str,
    provider: str,
    model_name: str,
    k: int,
    seed: int,
    status: str,
    meta: Dict,
) -> None:
    row = {
        "instance_id": iid,
        "provider": provider,
        "model": model_name,
        "attempt_index": k,
        "seed": seed,
        "status": status,
        "usage": meta,
        "ts": int(time.time()),
    }
    _write_line(attempts_log_path, row)
