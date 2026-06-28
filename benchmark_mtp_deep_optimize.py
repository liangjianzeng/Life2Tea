#!/usr/bin/env python3
"""
MTP 深度优化测试 - 针对速度瓶颈进行优化
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

def start_server(cmd, timeout=300):
    """启动 llama-server"""
    print(f"\n启动服务器...")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    # 等待服务器启动
    time.sleep(8)

    for _ in range(int(timeout/2)):
        try:
            req = urllib.request.Request(f"{BASE_URL}/health")
            resp = urllib.request.urlopen(req, timeout=2)
            if resp.status == 200:
                print("✓ 服务器已启动")
                time.sleep(2)
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
        try:
            process.wait(timeout=10)
        except:
            process.kill()
        time.sleep(2)

def benchmark(prompt, max_tokens=128):
    """快速 benchmark - 减少 token 数加快测试"""
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
    gen_time = (end_time - first_token_time) if first_token_time else total_time
    tok_s = token_count / gen_time if gen_time > 0 else 0

    return {
        "ttft_ms": ttft,
        "tok_s": tok_s,
        "total_tokens": token_count,
        "total_time_s": total_time
    }

def test_config(name, cmd, prompt="解释什么是人工智能？"):
    """测试单个配置"""
    print(f"\n{'='*70}")
    print(f"测试配置: {name}")
    print(f"{'='*70}")

    server = start_server(cmd)
    if not server:
        return None

    # 预热
    print("预热...")
    benchmark("Hi", max_tokens=10)

    # 正式测试
    print("正式测试...")
    result = benchmark(prompt, max_tokens=128)

    if result:
        print(f"  TTFT: {result['ttft_ms']:.1f}ms")
        print(f"  速度: {result['tok_s']:.1f} tok/s")
        print(f"  Token数: {result['total_tokens']}")

    stop_server(server)

    return result

def main():
    print("=" * 70)
    print("Qwen3.6-27B 深度优化测试")
    print("=" * 70)
    print("\n目标: 突破 15 tok/s")

    results = {}

    # 测试 1: 当前最佳配置（基准）
    print("\n\n【测试 1/6】基准配置")
    cmd1 = [
        LLAMA_SERVER,
        "--model", MODEL_PATH,
        "--port", "8088",
        "--host", "0.0.0.0",
        "--ctx-size", "4096",
        "--n-gpu-layers", "-1",
        "-t", "16",
        "--flash-attn", "on",
        "--reasoning", "off",
        "--no-warmup",
        "--spec-type", "draft-mtp",
        "--spec-draft-n-max", "2"
    ]
    result1 = test_config("基准 (MTP 2)", cmd1)
    if result1:
        results["基准 (MTP 2)"] = result1

    # 测试 2: 禁用 MTP，使用普通推理
    print("\n\n【测试 2/6】禁用 MTP")
    cmd2 = [
        LLAMA_SERVER,
        "--model", MODEL_PATH,
        "--port", "8088",
        "--host", "0.0.0.0",
        "--ctx-size", "4096",
        "--n-gpu-layers", "-1",
        "-t", "16",
        "--flash-attn", "on",
        "--reasoning", "off",
        "--no-warmup"
    ]
    result2 = test_config("禁用 MTP", cmd2)
    if result2:
        results["禁用 MTP"] = result2

    # 测试 3: 调整线程数
    print("\n\n【测试 3/6】调整线程数 (8)")
    cmd3 = [
        LLAMA_SERVER,
        "--model", MODEL_PATH,
        "--port", "8088",
        "--host", "0.0.0.0",
        "--ctx-size", "4096",
        "--n-gpu-layers", "-1",
        "-t", "8",
        "--flash-attn", "on",
        "--reasoning", "off",
        "--no-warmup",
        "--spec-type", "draft-mtp",
        "--spec-draft-n-max", "2"
    ]
    result3 = test_config("线程数 8", cmd3)
    if result3:
        results["线程数 8"] = result3

    # 测试 4: 调整线程数 (32)
    print("\n\n【测试 4/6】调整线程数 (32)")
    cmd4 = [
        LLAMA_SERVER,
        "--model", MODEL_PATH,
        "--port", "8088",
        "--host", "0.0.0.0",
        "--ctx-size", "4096",
        "--n-gpu-layers", "-1",
        "-t", "32",
        "--flash-attn", "on",
        "--reasoning", "off",
        "--no-warmup",
        "--spec-type", "draft-mtp",
        "--spec-draft-n-max", "2"
    ]
    result4 = test_config("线程数 32", cmd4)
    if result4:
        results["线程数 32"] = result4

    # 测试 5: 不使用 KV cache 量化
    print("\n\n【测试 5/6】不使用 KV cache 量化")
    cmd5 = [
        LLAMA_SERVER,
        "--model", MODEL_PATH,
        "--port", "8088",
        "--host", "0.0.0.0",
        "--ctx-size", "4096",
        "--n-gpu-layers", "-1",
        "-t", "16",
        "--flash-attn", "on",
        "--reasoning", "off",
        "--no-warmup",
        "--spec-type", "draft-mtp",
        "--spec-draft-n-max", "2"
    ]
    result5 = test_config("无 KV 量化", cmd5)
    if result5:
        results["无 KV 量化"] = result5

    # 测试 6: 检查是否有更激进的优化参数
    print("\n\n【测试 6/6】尝试 --no-mmap (锁定在内存)")
    cmd6 = [
        LLAMA_SERVER,
        "--model", MODEL_PATH,
        "--port", "8088",
        "--host", "0.0.0.0",
        "--ctx-size", "4096",
        "--n-gpu-layers", "-1",
        "-t", "16",
        "--flash-attn", "on",
        "--reasoning", "off",
        "--no-warmup",
        "--no-mmap",
        "--spec-type", "draft-mtp",
        "--spec-draft-n-max", "2"
    ]
    result6 = test_config("no-mmap", cmd6)
    if result6:
        results["no-mmap"] = result6

    # 生成报告
    print("\n\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)

    print(f"\n{'配置':<30} {'速度 (tok/s)':<20} {'TTFT (ms)':<15}")
    print("-" * 65)

    best_speed = 0
    best_config = ""

    for name, result in results.items():
        speed = result["tok_s"]
        ttft = result["ttft_ms"]
        print(f"{name:<30} {speed:<20.1f} {ttft:<15.1f}")

        if speed > best_speed:
            best_speed = speed
            best_config = name

    print("-" * 65)

    if best_config:
        print(f"\n🏆 最优配置: {best_config}")
        print(f"   速度: {best_speed:.1f} tok/s")
        if best_speed < 10:
            print(f"\n⚠️  警告: 速度仍然较低 ({best_speed:.1f} tok/s)")
            print(f"   可能原因:")
            print(f"   1. 模型规模过大 (27B)")
            print(f"   2. 内存带宽瓶颈 (GB10 LPDDR5X ~273 GB/s)")
            print(f"   3. 量化精度 (Q4_K_M)")

    # 保存结果
    result_file = "/home/jianzengliang/Models/deep_optimize_results.json"
    with open(result_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n详细结果已保存到: {result_file}")

    # 建议
    print(f"\n💡 优化建议:")
    print(f"   1. 尝试更小的模型 (如 Qwen3.6-14B)")
    print(f"   2. 使用更激进的量化 (Q3_K_M 或 Q2_K)")
    print(f"   3. 检查 GB10 的 GPU 频率是否达到最大值")
    print(f"   4. 考虑使用 Ollama 的 Flash Attention 优化版本")

if __name__ == "__main__":
    main()
