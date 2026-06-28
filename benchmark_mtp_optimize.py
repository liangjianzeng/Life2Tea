#!/usr/bin/env python3
"""
MTP 优化测试 - 尝试不同配置找到最优性能
"""

import urllib.request
import json
import time
import subprocess
import sys
import os

BASE_URL = "http://127.0.0.1:8088"
MODEL_PATH = "/home/jianzengliang/Models/Qwen3.6-27B-Q4_K_M-mtp.gguf"
LLAMA_SERVER = "/home/jianzengliang/llama.cpp/build/bin/llama-server"

def start_server(cmd):
    """启动 llama-server"""
    print(f"\n启动服务器...")
    print(f"命令: {' '.join(cmd)}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    # 等待服务器启动
    time.sleep(10)

    for _ in range(30):
        try:
            req = urllib.request.Request(f"{BASE_URL}/health")
            resp = urllib.request.urlopen(req, timeout=2)
            if resp.status == 200:
                print("✓ 服务器已启动")
                time.sleep(3)
                return process
        except:
            time.sleep(2)

    print("✗ 服务器启动失败")
    process.terminate()
    return None

def stop_server(process):
    """停止 llama-server"""
    if process:
        print("停止服务器...")
        process.terminate()
        process.wait()
        time.sleep(2)

def benchmark(prompt, max_tokens=256):
    """快速 benchmark"""
    payload = {
        "model": "qwen3.6-27b-mtp",
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
    tok_s = token_count / (end_time - first_token_time) if first_token_time else 0

    return {
        "ttft_ms": ttft,
        "tok_s": tok_s,
        "total_tokens": token_count,
        "total_time_s": total_time
    }

def monitor_gpu(process_id, duration=10):
    """监控 GPU 利用率"""
    print(f"  监控 GPU (进程 {process_id})...")

    gpu_utils = []
    for _ in range(duration):
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            util = int(result.stdout.strip())
            gpu_utils.append(util)
            time.sleep(1)
        except:
            break

    if gpu_utils:
        avg_util = sum(gpu_utils) / len(gpu_utils)
        max_util = max(gpu_utils)
        print(f"  GPU 平均利用率: {avg_util:.1f}%, 最高: {max_util}%")
        return avg_util
    return 0

def test_config(name, cmd, prompt="解释什么是人工智能？"):
    """测试单个配置"""
    print(f"\n{'='*60}")
    print(f"测试配置: {name}")
    print(f"{'='*60}")

    server = start_server(cmd)
    if not server:
        return None

    # 获取进程 ID
    pid = server.pid

    # 预热
    print("预热...")
    benchmark("Hi", max_tokens=10)

    # 正式测试（在后台监控 GPU）
    print("正式测试...")
    result = benchmark(prompt, max_tokens=256)

    if result:
        print(f"  TTFT: {result['ttft_ms']:.1f}ms")
        print(f"  速度: {result['tok_s']:.1f} tok/s")
        print(f"  Token数: {result['total_tokens']}")

    stop_server(server)

    return result

def main():
    print("=" * 60)
    print("Qwen3.6-27B 优化配置测试")
    print("=" * 60)

    # 基础命令部分
    base_cmd = [
        LLAMA_SERVER,
        "--model", MODEL_PATH,
        "--port", "8088",
        "--host", "0.0.0.0",
        "--n-gpu-layers", "-1",
        "-t", "16",
        "--flash-attn", "on",
        "--reasoning", "off",
        "--no-warmup"
    ]

    configs = []

    # 配置 1: 当前配置 (8192 ctx, MTP 2)
    configs.append({
        "name": "当前配置 (8192 ctx, MTP 2)",
        "cmd": base_cmd + ["--ctx-size", "8192", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0", "--spec-type", "draft-mtp", "--spec-draft-n-max", "2"]
    })

    # 配置 2: 减小上下文 (4096 ctx)
    configs.append({
        "name": "优化1 (4096 ctx, MTP 2)",
        "cmd": base_cmd + ["--ctx-size", "4096", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0", "--spec-type", "draft-mtp", "--spec-draft-n-max", "2"]
    })

    # 配置 3: 增加 MTP 推测数 (4)
    configs.append({
        "name": "优化2 (4096 ctx, MTP 4)",
        "cmd": base_cmd + ["--ctx-size", "4096", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0", "--spec-type", "draft-mtp", "--spec-draft-n-max", "4"]
    })

    # 配置 4: 不使用 flash attention
    configs.append({
        "name": "优化3 (4096 ctx, MTP 4, 无flash)",
        "cmd": base_cmd + ["--ctx-size", "4096", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0", "--spec-type", "draft-mtp", "--spec-draft-n-max", "4", "--flash-attn", "off"]
    })

    # 配置 5: 减小 GPU 层数（如果 VRAM 不够）
    configs.append({
        "name": "优化4 (4096 ctx, MTP 4, 60 layers)",
        "cmd": base_cmd + ["--ctx-size", "4096", "--n-gpu-layers", "60", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0", "--spec-type", "draft-mtp", "--spec-draft-n-max", "4"]
    })

    results = {}

    for config in configs:
        result = test_config(config["name"], config["cmd"])
        if result:
            results[config["name"]] = result

    # 生成报告
    print("\n\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    print(f"\n{'配置':<40} {'速度 (tok/s)':<20} {'TTFT (ms)':<15}")
    print("-" * 75)

    best_speed = 0
    best_config = ""

    for name, result in results.items():
        speed = result["tok_s"]
        ttft = result["ttft_ms"]
        print(f"{name:<40} {speed:<20.1f} {ttft:<15.1f}")

        if speed > best_speed:
            best_speed = speed
            best_config = name

    print("-" * 75)

    if best_config:
        print(f"\n🏆 最优配置: {best_config}")
        print(f"   速度: {best_speed:.1f} tok/s")

    # 保存结果
    result_file = "/home/jianzengliang/Models/optimized_benchmark_results.json"
    with open(result_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n详细结果已保存到: {result_file}")

if __name__ == "__main__":
    main()
