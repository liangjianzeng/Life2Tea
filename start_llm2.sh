#!/bin/bash
# start_llm2.sh - Manual fallback to launch llama-server on Unix-like systems
# Usage: ./start_llm2.sh [port]

LLAMA_EXE="${LLAMA_EXE:-./llama-server}"
MODEL_PATH="${MODEL_PATH:-./models/LFM2-24B-A2B-Q4_K_M.gguf}"
PORT="${1:-8082}"
NGL="${NGL:-28}"
CTX="${CTX:-20480}"
THREADS="${THREADS:-8}"

echo "Starting llama-server on port ${PORT}..."
echo "  EXE:   ${LLAMA_EXE}"
echo "  Model: ${MODEL_PATH}"
echo "  NGL=${NGL} CTX=${CTX} Threads=${THREADS}"

# Start llama-server in background
"${LLAMA_EXE}" \
  --port "${PORT}" \
  --model "${MODEL_PATH}" \
  -ngl "${NGL}" \
  -c "${CTX}" \
  --parallel 1 \
  --threads "${THREADS}" \
  -b 1024 \
  -ub 512 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --no-warmup \
  --temp 0.2 \
  --top-k 80 \
  --top-p 0.9 \
  --min-p 0.0 \
  --repeat-penalty 1.05 \
  --alias lfm2 &

LLAMA_PID=$!
echo "llama-server started in background (PID: ${LLAMA_PID})"
echo "Waiting 30-60s for model to load..."
sleep 60
echo "Testing health endpoint:"
curl -s "http://127.0.0.1:${PORT}/health"
