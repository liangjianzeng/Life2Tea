#!/usr/bin/env python3
"""
对比测试：qwen3-coder-next vs lfm2 的工具理解能力
测试 Function Calling 的准确性、参数完整性、任务分解能力
"""

import json
import urllib.request
import urllib.error
import time

BASE_URL = "http://127.0.0.1:11434"

# 定义的工具（模拟编程智能体的真实工具）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容。用于查看现有代码、配置文件、文档等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件的绝对路径或相对于项目的路径"
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入或创建文件。用于生成新代码、修改配置文件等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件内容"}
                },
                "required": ["file_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "执行 shell 命令。用于运行测试、安装依赖、启动服务等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                    "timeout": {"type": "number", "description": "超时时间（秒），默认 30"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "在代码库中搜索关键词、函数名、类名等。用于理解现有代码结构。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "file_pattern": {"type": "string", "description": "文件匹配模式，如 *.py、*.ts"}
                },
                "required": ["query"]
            }
        }
    }
]

# 测试用例
TEST_CASES = [
    {
        "name": "简单工具调用（单次）",
        "prompt": "帮我查看 package.json 的内容",
        "expected_tool": "read_file",
        "expected_params": {"file_path": "package.json"}
    },
    {
        "name": "复合工具调用（多次）",
        "prompt": "创建一个新的 Python 项目，先创建 main.py，然后运行 pip install requests",
        "expected_tools": ["write_file", "run_command"],
        "description": "应该调用两个工具"
    },
    {
        "name": "工具参数准确性",
        "prompt": "在 src 目录下搜索所有包含 'Router' 的 TypeScript 文件",
        "expected_tool": "search_codebase",
        "expected_params": {"query": "Router", "file_pattern": "*.ts"}
    },
    {
        "name": "任务分解能力",
        "prompt": "我要修复一个 bug：用户登录后页面白屏。帮我分析可能的原因并排查",
        "description": "应该先搜索相关代码，再读取关键文件，最后给出修复方案"
    },
    {
        "name": "工具选择合理性",
        "prompt": "帮我运行 npm test 看看测试是否通过",
        "expected_tool": "run_command",
        "expected_params": {"command": "npm test"}
    }
]

def call_model_with_tools(model, prompt, tools, history=None):
    """调用模型，传入工具定义，返回模型选择的工具"""
    messages = history or []
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 500
        }
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        end = time.time()
        
        message = result.get("message", {})
        tool_calls = message.get("tool_calls", [])
        
        return {
            "success": True,
            "tool_calls": tool_calls,
            "content": message.get("content", ""),
            "time": end - start
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def evaluate_tool_call(test_case, result):
    """评估工具调用的准确性"""
    if not result["success"]:
        return {"score": 0, "reason": f"调用失败: {result.get('error', '未知错误')}"}
    
    tool_calls = result.get("tool_calls", [])
    
    if not tool_calls:
        return {"score": 1, "reason": "未调用工具（可能直接回答）"}
    
    # 简单评分逻辑
    score = 0
    reasons = []
    
    # 检查是否调用了预期的工具
    if "expected_tool" in test_case:
        expected = test_case["expected_tool"]
        actual = [tc.get("function", {}).get("name") for tc in tool_calls]
        if expected in actual:
            score += 3
            reasons.append(f"✅ 正确调用了 {expected}")
        else:
            reasons.append(f"❌ 预期 {expected}，实际 {actual}")
    
    # 检查参数准确性
    if "expected_params" in test_case and tool_calls:
        expected_params = test_case["expected_params"]
        actual_params = tool_calls[0].get("function", {}).get("arguments", {})
        
        if isinstance(actual_params, str):
            try:
                actual_params = json.loads(actual_params)
            except:
                actual_params = {}
        
        param_score = 0
        for key, expected_val in expected_params.items():
            if key in actual_params:
                actual_val = actual_params[key]
                if expected_val in actual_val or actual_val in expected_val:
                    param_score += 1
                    reasons.append(f"✅ 参数 {key} 正确")
                else:
                    reasons.append(f"⚠️ 参数 {key} 可能不准确: 预期 {expected_val}, 实际 {actual_val}")
        
        score += param_score
    
    return {"score": score, "reason": "; ".join(reasons), "tool_calls": tool_calls}

def main():
    models = ["qwen3-coder-next:latest", "lfm2:latest"]
    
    print("=" * 70)
    print("🔬 工具理解能力对比测试")
    print("=" * 70)
    print()
    
    results = {model: [] for model in models}
    
    for test_case in TEST_CASES:
        print(f"📋 测试用例: {test_case['name']}")
        print(f"   提示: {test_case['prompt']}")
        print()
        
        for model in models:
            print(f"  🤖 {model}:")
            result = call_model_with_tools(model, test_case["prompt"], TOOLS)
            
            evaluation = evaluate_tool_call(test_case, result)
            
            if result["success"]:
                tool_calls = result.get("tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        func_name = tc.get("function", {}).get("name", "")
                        func_args = tc.get("function", {}).get("arguments", {})
                        print(f"    调用工具: {func_name}")
                        print(f"    参数: {json.dumps(func_args, ensure_ascii=False)[:200]}")
                else:
                    print(f"    未调用工具，直接回答: {result.get('content', '')[:100]}")
                
                print(f"    耗时: {result['time']:.2f}s")
            else:
                print(f"    ❌ 调用失败: {result.get('error', '')}")
            
            print(f"    评分: {evaluation['score']} - {evaluation['reason']}")
            print()
            
            results[model].append({
                "test": test_case["name"],
                "result": result,
                "evaluation": evaluation
            })
    
    # 汇总评分
    print("=" * 70)
    print("📊 汇总评分")
    print("=" * 70)
    print()
    
    for model in models:
        total_score = sum([r["evaluation"]["score"] for r in results[model]])
        avg_time = sum([r["result"].get("time", 0) for r in results[model] if r["result"]["success"]]) / len(results[model])
        
        print(f"🤖 {model}")
        print(f"   总评分: {total_score} / 25")
        print(f"   平均耗时: {avg_time:.2f}s")
        print(f"   工具调用成功率: {sum([1 for r in results[model] if r['result'].get('tool_calls', [])])} / {len(results[model])}")
        print()
    
    # 保存详细结果
    with open("/tmp/tool_understanding_result.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("✅ 详细结果已保存到 /tmp/tool_understanding_result.json")

if __name__ == "__main__":
    main()
