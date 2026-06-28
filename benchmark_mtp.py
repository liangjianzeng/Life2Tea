#!/usr/bin/env python3
"""
MTP (Multi-Token Prediction) 加速性能测试
对比启用/禁用 MTP 的推理速度
"""

import urllib.request
import json
import time
import sys
import subprocess
import os
import signal

BASE_URL = "http://127.0.0.1:8088"
MODEL_PATH = "/home/jianzengliang/Models/Qwen3.6-27B-Q4_K_M-mtp.gguf"
LLAMA_SERVER = "/home/jianzengliang/llama.cpp/build/bin/llama-server"

# 测试提示词（3种长度）
TEST_PROMPTS = {
    "short": "解释什么是人工智能？",
    "medium": "请详细解释机器学习中的梯度下降算法，包括其基本原理、优缺点，以及在深度学习中的应用。",
    "long": """请写一篇关于大语言模型的技术综述，包括以下几个方面：
1. 大语言模型的发展历程
2. Transformer架构的核心创新
3. 主流开源模型（如LLaMA、Qwen、DeepSeek等）的特点
4. 推理优化技术（量化、推测解码、KV Cache等）
5. 未来发展趋势
请详细展开每个方面，给出深入的技术分析。"""
}

def start_server(use_mtp=True, port=8088):
    """启动 llama-server"""
    cmd = [
        LLAMA_SERVER,
        "--model", MODEL_PATH,
        "--port", str(port),
        "--host", "0.0.0.0",
        "--ctx-size", "8192",
        "--n-gpu-layers", "-1",
        "--parallel", "1",
        "-t", "16",
        "--cache-type-k", "q8_0",
        "--cache-type-v", "q8_0",
        "--flash-attn", "on",
        "--reasoning", "off",
        "--no-warmup"
    ]

    if use_mtp:
        cmd.extend(["--spec-type", "draft-mtp", "--spec-draft-n-max", "2"])

    print(f"\n{'='*60}")
    print(f"启动服务器 {'[MTP 启用]' if use_mtp else '[MTP 禁用]'}")
    print(f"命令: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    # 等待服务器启动
    print("等待服务器启动...")
    time.sleep(10)

    # 检查服务器是否就绪
    for _ in range(30):
        try:
            req = urllib.request.Request(f"{BASE_URL}/health")
            resp = urllib.request.urlopen(req, timeout=2)
            if resp.status == 200:
                print("✓ 服务器已启动")
                time.sleep(5)  # 额外等待预热
                return process
        except:
            time.sleep(2)

    print("✗ 服务器启动失败")
    process.terminate()
    return None

def stop_server(process):
    """停止 llama-server"""
    if process:
        print("\n停止服务器...")
        process.terminate()
        process.wait()
        time.sleep(3)

def benchmark_prompt(prompt, use_mtp=True):
    """测试单个提示词的性能"""
    payload = {
        "model": "qwen3.6-27b-mtp",
        "prompt": prompt,
        "max_tokens": 512,
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
    tokens = []

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
                                tokens.append(choice["text"])
                    except:
                        pass
    except Exception as e:
        print(f"  错误: {e}")
        return None

    end_time = time.time()
    total_time = end_time - start_time
    ttft = (first_token_time - start_time) * 1000 if first_token_time else 0
    tok_s = token_count / (end_time - first_token_time) if first_token_time else 0

    return {
        "ttft_ms": ttft,
        "tok_s": tok_s,
        "total_tokens": token_count,
        "total_time_s": total_time
    }

def run_benchmark(use_mtp=True):
    """运行完整基准测试"""
    results = {}

    for prompt_name, prompt in TEST_PROMPTS.items():
        print(f"\n测试 [{prompt_name}] {'[MTP]' if use_mtp else '[NO-MTP]'}...")
        result = benchmark_prompt(prompt, use_mtp)
        if result:
            results[prompt_name] = result
            print(f"  TTFT: {result['ttft_ms']:.1f}ms")
            print(f"  速度: {result['tok_s']:.1f} tok/s")
            print(f"  Token数: {result['total_tokens']}")

    return results

def main():
    print("=" * 60)
    print("Qwen3.6-27B MTP 加速性能测试")
    print("=" * 60)

    all_results = {}

    # 测试 1: 禁用 MTP
    print("\n\n【阶段 1/2】测试 禁用 MTP...")
    server = start_server(use_mtp=False)
    if server:
        all_results["no_mtp"] = run_benchmark(use_mtp=False)
        stop_server(server)
    else:
        print("无法启动服务器（无 MTP），跳过...")
        all_results["no_mtp"] = None

    # 测试 2: 启用 MTP
    print("\n\n【阶段 2/2】测试 启用 MTP...")
    server = start_server(use_mtp=True)
    if server:
        all_results["with_mtp"] = run_benchmark(use_mtp=True)
        stop_server(server)
    else:
        print("无法启动服务器（有 MTP），跳过...")
        all_results["with_mtp"] = None

    # 生成报告
    print("\n\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    if all_results["no_mtp"] and all_results["with_mtp"]:
        print(f"\n{'测试项':<15} {'无MTP (tok/s)':<20} {'有MTP (tok/s)':<20} {'加速比':<10}")
        print("-" * 70)

        for prompt_name in TEST_PROMPTS.keys():
            if prompt_name in all_results["no_mtp"] and prompt_name in all_results["with_mtp"]:
                no_mtp_speed = all_results["no_mtp"][prompt_name]["tok_s"]
                with_mtp_speed = all_results["with_mtp"][prompt_name]["tok_s"]
                speedup = with_mtp_speed / no_mtp_speed if no_mtp_speed > 0 else 0

                print(f"{prompt_name:<15} {no_mtp_speed:<20.1f} {with_mtp_speed:<20.1f} {speedup:<10.2f}x")

        # 计算平均加速比
        speedups = []
        for prompt_name in TEST_PROMPTS.keys():
            if prompt_name in all_results["no_mtp"] and prompt_name in all_results["with_mtp"]:
                no_mtp_speed = all_results["no_mtp"][prompt_name]["tok_s"]
                with_mtp_speed = all_results["with_mtp"][prompt_name]["tok_s"]
                speedups.append(with_mtp_speed / no_mtp_speed if no_mtp_speed > 0 else 0)

        if speedups:
            avg_speedup = sum(speedups) / len(speedups)
            print("-" * 70)
            print(f"{'平均加速比':<15} {'':<20} {'':<20} {avg_speedup:<10.2f}x")

    # 保存详细结果
    result_file = "/home/jianzengliang/Models/mtp_benchmark_results.json"
    with open(result_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\n详细结果已保存到: {result_file}")

if __name__ == "__main__":
    main()
