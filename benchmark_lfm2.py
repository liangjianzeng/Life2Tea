#!/usr/bin/env python3
"""
Benchmark LFM2 model on remote Ollama server.
Tests: Short/Medium/Long prompts, 3 runs each.
"""

import json
import time
import urllib.request
import urllib.error
import statistics

BASE_URL = "http://127.0.0.1:11434"
MODEL = "lfm2:latest"

TESTS = [
    {
        "name": "Short Prompt (50 tokens)",
        "prompt": "Explain quantum computing in 3 sentences.",
        "max_tokens": 100,
    },
    {
        "name": "Medium Prompt (500 tokens)",
        "prompt": "Write a detailed analysis of the benefits and drawbacks of renewable energy sources. Consider solar, wind, hydro, and geothermal. Discuss environmental impact, cost, scalability, and reliability. Provide specific examples and data where possible.",
        "max_tokens": 200,
    },
    {
        "name": "Long Prompt (2000 tokens)",
        "prompt": "Analyze the following comprehensive business strategy and provide detailed feedback:\n\n" + "We are a mid-sized technology company specializing in cloud infrastructure. Our strategy includes: (1) Expanding to emerging markets in Southeast Asia and Latin America over the next 3 years. (2) Investing $50M in R&D for edge computing and AI-driven automation. (3) Forming strategic partnerships with local telecom providers. (4) Developing a subscription-based SaaS platform for enterprise clients. (5) Implementing a comprehensive sustainability initiative to achieve carbon neutrality by 2030. Please analyze each component, identify potential risks, suggest improvements, and provide a roadmap for execution. Consider market trends, competitive landscape, regulatory requirements, and financial projections." + "Additional context: " + "Our target market includes enterprises with 500-5000 employees. " * 20,
        "max_tokens": 300,
    },
]

def run_test(test_case, model):
    """Run a single test and return metrics."""
    payload = {
        "model": model,
        "prompt": test_case["prompt"],
        "stream": False,
        "options": {
            "num_predict": test_case["max_tokens"],
            "temperature": 0.3,
        }
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    
    start = time.time()
    first_token_time = None
    chunk_times = []
    
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            full_response = json.loads(resp.read().decode("utf-8"))
            
        end = time.time()
        total_time = end - start
        
        # Ollama returns full response at once (non-streaming)
        # We need to estimate tokens from response length
        response_text = full_response.get("response", "")
        eval_count = full_response.get("eval_count", 0)
        eval_duration = full_response.get("eval_duration", 0)
        
        if eval_count > 0 and eval_duration > 0:
            tok_per_sec = eval_count / (eval_duration / 1e9)
        else:
            # Fallback: estimate from response length
            est_tokens = len(response_text.split()) * 1.3  # Rough estimate
            tok_per_sec = est_tokens / total_time
            
        return {
            "total_time": total_time,
            "tok_per_sec": tok_per_sec,
            "eval_count": eval_count,
            "response_length": len(response_text),
        }
        
    except Exception as e:
        return {"error": str(e)}

def main():
    print(f"=== LFM2 Benchmark on DGX Spark ===")
    print(f"Model: {MODEL}")
    print(f"Server: {BASE_URL}")
    print()
    
    results = {}
    
    for test in TESTS:
        print(f"📊 {test['name']}")
        test_results = []
        
        for i in range(3):
            print(f"  Run {i+1}/3...", end=" ", flush=True)
            result = run_test(test, MODEL)
            
            if "error" in result:
                print(f"❌ {result['error']}")
            else:
                print(f"✅ {result['tok_per_sec']:.1f} tok/s")
                test_results.append(result)
        
        if test_results:
            avg_tok = statistics.mean([r["tok_per_sec"] for r in test_results])
            results[test["name"]] = {
                "avg_tok_per_sec": avg_tok,
                "runs": test_results,
            }
        print()
    
    # Print summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for test_name, data in results.items():
        print(f"{test_name}: {data['avg_tok_per_sec']:.1f} tok/s")
    
    # Save to file
    with open("/tmp/benchmark_lfm2_result.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n✅ Results saved to /tmp/benchmark_lfm2_result.json")

if __name__ == "__main__":
    main()
