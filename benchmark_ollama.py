#!/usr/bin/env python3
"""
benchmark_ollama.py — Benchmark ollama models via HTTP API (localhost)
Usage: python3 benchmark_ollama.py
Requires: Python 3.6+ (stdlib only, no pip needed)
"""
import json
import time
import statistics
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:11434"
MODELS = [
    "qwen3.6:35b",
    "qwen3-coder-next:latest",
    "glm-4.7-flash:latest",
]

TEST_PROMPTS = [
    ("短问答", "用一句话解释什么是机器学习。", 256),
    ("代码生成", "用Python写一个快速排序函数，并加上中文注释。", 512),
    ("长文生成", "写一篇500字左右的短文，介绍人工智能的发展历史。", 1024),
]


def api_generate(model, prompt, max_tokens):
    """Call ollama /api/generate, return (prompt_tokens, completion_tokens, total_s, eval_s)."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.0},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return None, None, None, str(e)
    elapsed = time.perf_counter() - start
    prompt_count = data.get("prompt_eval_count", 0)
    eval_count = data.get("eval_count", 0)
    eval_dur_ns = data.get("eval_duration", 0)
    eval_s = eval_dur_ns / 1e9 if eval_dur_ns else 0
    return prompt_count, eval_count, elapsed, eval_s


def test_model(model, prompt, max_tokens, num_runs=3):
    results = []
    for i in range(num_runs):
        prompt_tok, comp_tok, total_s, eval_s = api_generate(model, prompt, max_tokens)
        if prompt_tok is None:
            results.append({"run": i + 1, "error": str(total_s)})
        else:
            tok_s = comp_tok / eval_s if eval_s > 0 else 0
            results.append({
                "run": i + 1,
                "prompt_tokens": prompt_tok,
                "completion_tokens": comp_tok,
                "total_s": round(total_s, 2),
                "tok_s": round(tok_s, 1),
            })
    return results


def main():
    print("=" * 72)
    print("  Ollama Model Benchmark — DGX Spark")
    print("  Base URL:", BASE_URL)
    print("=" * 72)

    # Check API accessible
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
            model_names = [m["name"] for m in tags.get("models", [])]
        print(f"  API accessible, {len(model_names)} models found")
    except Exception as e:
        print(f"  ERROR: Cannot reach Ollama API at {BASE_URL}: {e}")
        return

    all_results = {}
    for model in MODELS:
        print(f"\n{'─' * 72}")
        print(f"  Model: {model}")
        print(f"{'─' * 72}")
        model_results = {}
        for tname, prompt, max_tok in TEST_PROMPTS:
            print(f"\n  Test: {tname}  (max_tokens={max_tok})")
            runs = test_model(model, prompt, max_tok)
            ok = [r for r in runs if "error" not in r]
            if ok:
                tok_s = [r["tok_s"] for r in ok]
                total_s = [r["total_s"] for r in ok]
                avg_tok = round(statistics.mean(tok_s), 1)
                avg_time = round(statistics.mean(total_s), 2)
                print(f"    tok/s: min={min(tok_s):.1f}  avg={avg_tok}  max={max(tok_s):.1f}")
                print(f"    time(s): min={min(total_s):.2f}  avg={avg_time}  max={max(total_s):.2f}")
                for r in ok:
                    print(f"      Run {r['run']}: {r['completion_tokens']}tok / {r['total_s']}s = {r['tok_s']} tok/s")
            else:
                errs = [r.get("error", "?") for r in runs]
                print(f"    ERROR: {errs}")
            model_results[tname] = runs
        all_results[model] = model_results

    # Summary table
    print(f"\n{'=' * 72}")
    print("  SUMMARY — Average tok/s (higher = better)")
    print(f"{'=' * 72}")
    hdr = f"  {'Model':<36} {'短问答':>8} {'代码生成':>8} {'长文生成':>8}"
    print(hdr)
    print("  " + "─" * 68)
    for model in MODELS:
        col = ""
        for _, tname, _ in TEST_PROMPTS:
            runs = all_results.get(model, {}).get(tname, [])
            ok = [r for r in runs if "error" not in r]
            if ok:
                avg = round(statistics.mean([r["tok_s"] for r in ok]), 1)
                col += f" {avg:>8.1f}"
            else:
                col += f" {'ERR':>8}"
        print(f"  {model:<36}{col}")
    print()


if __name__ == "__main__":
    main()
