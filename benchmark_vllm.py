#!/usr/bin/env python3
"""
测试 vLLM 推理速度（对比 llama.cpp）
"""

import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:8100"

TEST_PROMPTS = [
    "解释什么是人工智能？",
    "请详细解释机器学习中的梯度下降算法。",
    "请写一篇关于大语言模型的技术综述，包括发展历程、Transformer架构、主流开源模型等。"
]

def benchmark(prompt, max_tokens=256):
    """测试单个提示词"""
    payload = {
        "model": "/home/jianzengliang/Models/Qwen3.6-35B-A3B-FP8",
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
    print("vLLM 推理性能测试")
    print("=" * 60)
    print(f"模型: Qwen3.6-35B-A3B-FP8 (MoE, 3B active)")
    print(f"端点: {BASE_URL}")
    print()

    results = []

    # 预热
    print("预热...")
    benchmark("Hi", max_tokens=10)
    time.sleep(2)

    # 正式测试
    for i, prompt in enumerate(TEST_PROMPTS):
        print(f"\n测试 {i+1}/3...")
        print(f"提示词: {prompt[:50]}...")

        result = benchmark(prompt, max_tokens=256)

        if result:
            results.append(result)
            print(f"  TTFT: {result['ttft_ms']:.1f}ms")
            print(f"  速度: {result['tok_s']:.1f} tok/s")
            print(f"  Token数: {result['total_tokens']}")

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    if results:
        avg_speed = sum(r["tok_s"] for r in results) / len(results)
        avg_ttft = sum(r["ttft_ms"] for r in results) / len(results)

        print(f"\n平均推理速度: {avg_speed:.1f} tok/s")
        print(f"平均 TTFT: {avg_ttft:.1f} ms")

        print(f"\n对比 llama.cpp (Qwen3.6-27B):")
        print(f"  llama.cpp (禁用 MTP): 11.8 tok/s")
        print(f"  vLLM (MoE 3B active): {avg_speed:.1f} tok/s")
        print(f"  加速比: {avg_speed/11.8:.2f}x")

        if avg_speed > 11.8:
            print(f"\n✅ vLLM 更快！加速了 {avg_speed/11.8:.2f}x")
        else:
            print(f"\n⚠️  vLLM 反而更慢（可能配置问题）")

    # 保存结果
    result_file = "/home/jianzengliang/Models/vllm_benchmark_results.json"
    with open(result_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n详细结果已保存到: {result_file}")

if __name__ == "__main__":
    main()
