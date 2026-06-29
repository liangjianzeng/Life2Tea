#!/bin/bash
# benchmark_ollama.sh — Benchmark ollama models via API
# Usage: bash benchmark_ollama.sh

BASE="<http://127.0.0.1:11434>"
MODELS=( "qwen3.6:35b" "qwen3-coder-next:latest" "glm-4.7-flash:latest" )
PROMPTS=(
  "用一句话解释什么是机器学习。"
  "用Python写一个快速排序函数，并加上中文注释。"
  "写一篇500字左右的短文，介绍人工智能的发展历史。"
)

echo "======================================================================"
echo "  Ollama Model Benchmark — DGX Spark"
echo "======================================================================"
echo ""

# Check API accessible
if ! curl -s --connect-timeout 5 "$BASE/api/tags" > /dev/null 2>&1; then
    echo "ERROR: Ollama API not accessible at $BASE"
    echo "Is ollama serving on port 11434?"
    exit 1
fi

declare -A RESULTS  # model -> test_name -> "tok_s avg"

for model in "${MODELS[@]}"; do
    echo "──────────────────────────────────────────────────────────────────────────"
    echo "  Model: $model"
    echo "──────────────────────────────────────────────────────────────────────────"

    for i in 0 1 2; do
        pname=""
        case $i in
            0) pname="短问答";;
            1) pname="代码生成";;
            2) pname="长文生成";;
        esac
        prompt="${PROMPTS[$i]}"
        case $i in
            0) max_tok=256;;
            1) max_tok=512;;
            2) max_tok=1024;;
        esac

        echo ""
        echo "  Test: $pname (max_tokens=$max_tok)"
        echo -n "    "

        tok_s_list=""
        for run in 1 2 3; do
            payload="{\"model\":\"$model\",\"prompt\":\"$prompt\",\"stream\":false,\"options\":{\"num_predict\":$max_tok,\"temperature\":0.0}}"
            start_ts=$(date +%s%N)
            resp=$(curl -s -X POST "$BASE/api/generate" \
                -H "Content-Type: application/json" \
                -d "$payload" \
                --max-time 300 2>/dev/null)
            end_ts=$(date +%s%N)
            elapsed_ns=$((end_ts - start_ts))
            elapsed_s=$(echo "scale=3; $elapsed_ns / 1000000000" | bc)

            # Extract token counts from response
            eval_count=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('eval_count',0))" 2>/dev/null || echo "0")
            eval_dur=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('eval_duration',0))" 2>/dev/null || echo "0")

            if [ "$eval_dur" != "0" ] && [ "$eval_dur" != "" ]; then
                tok_s=$(echo "scale=1; $eval_count / ($eval_dur / 1000000000)" | bc 2>/dev/null)
                printf "Run%d:%s " "$run" "$tok_s"
                tok_s_list="$tok_s_list $tok_s"
            else
                printf "Run%d:ERR " "$run"
            fi
        done
        # Average
        if [ -n "$tok_s_list" ]; then
            avg=$(echo "$tok_s_list" | tr ' ' '\n' | grep -v '^$' | awk '{sum+=$1; n++} END {if(n>0) printf "%.1f", sum/n}')
            echo ""
            echo "    → avg $avg tok/s"
        fi
    done
    echo ""
done

echo "======================================================================"
echo "  SUMMARY"
echo "======================================================================"
echo ""
printf "  %-35s %10s %10s %10s\n" "Model" "短问答" "代码生成" "长文生成"
echo "  ----------------------------------------------------------------------"

for model in "${MODELS[@]}"; do
    printf "  %-35s %10s %10s %10s\n" "$model" "..." "..." "..."
done
echo ""
