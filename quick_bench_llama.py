#!/usr/bin/env python3
"""快速测试 llama.cpp 速度（vLLM 已停止）"""

import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:8088"

def benchmark(prompt, max_tokens=256):
    payload = {
        "model": "qwen3.6-27b",
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": True
    }

    req = urllib.request.Request(
        f"{BASE_URL}/v1/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )

    start_time = time.time()
    first_token_time = None
    token_count = 0

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for line in resp:
                line = line.decode().strip()
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        if "choices" in data and len(data["choices"]) > 0:
                            choice = data["choices"][0]
                            if "text" in choice and choice["text"]:
                                if first_token_time is None:
                                    first_token_time = time.time()
                                token_count += 1
                    except:
                        pass
    except Exception as e:
        print(f"  错误: {e}")
        return None

    end_time = time.time()
    total_time = end_time - start_time
    ttft = (first_token_time - start_time) * 1000 if first_token_time else 0
    gen_time = (end_time - first_token_time) if first_token_time else total_time
    tok_s = token_count / gen_time if gen_time > 0 else 0

    return {
        "ttft_ms": ttft,
        "tok_s": tok_s,
        "total_tokens": token_count,
        "total_time_s": total_time
    }

def main():
    print("=" * 60)
    print("llama.cpp 速度测试（vLLM 已停止）")
    print("=" * 60)

    # 预热
    print("\n预热...")
    benchmark("Hi", max_tokens=10)
    time.sleep(2)

    # 测试
    prompt = "解释什么是人工智能？"
    print(f"\n测试: {prompt}")
    print("-" * 60)

    # 跑 3 次取平均
    results = []
    for i in range(3):
        print(f"\n第 {i+1} 次测试...")
        result = benchmark(prompt, max_tokens=256)
        if result:
            results.append(result)
            print(f"  TTFT: {result['ttft_ms']:.1f}ms")
            print(f"  速度: {result['tok_s']:.1f} tok/s")
            print(f"  Token数: {result['total_tokens']}")

    # 汇总
    if results:
        avg_speed = sum(r["tok_s"] for r in results) / len(results)
        avg_ttft = sum(r["ttft_ms"] for r in results) / len(results)

        print("\n" + "=" * 60)
        print("汇总")
        print("=" * 60)
        print(f"\n平均推理速度: {avg_speed:.1f} tok/s")
        print(f"平均 TTFT: {avg_ttft:.1f} ms")

        print(f"\n对比之前的结果:")
        print(f"  之前 (可能 vLLM 在运行): 9-12 tok/s")
        print(f"  现在 (vLLM 已停止): {avg_speed:.1f} tok/s")

        if abs(avg_speed - 11.8) < 2:
            print(f"\n✅ 速度没有明显改善")
            print(f"   说明之前慢不是因为 vLLM")
        else:
            print(f"\n🎯 速度有变化！")
            print(f"   可能之前确实受 vLLM 影响")

if __name__ == "__main__":
    main()
