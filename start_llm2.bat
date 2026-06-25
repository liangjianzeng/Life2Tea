@echo off
REM Start llama-server.exe for lfm2 model
REM Run this script manually if backend fails to start the process

set LLAMA_EXE=D:\MyLLM\llama.cpp\llama-server.exe
set MODEL_PATH=D:\MyLLM\models\LFM2-24B-A2B-Q4_K_M.gguf
set PORT=8082

echo Starting llama-server.exe on port %PORT%...
start "Life2Tea-llm2" /B "%LLAMA_EXE%" ^
  --port %PORT% ^
  --model "%MODEL_PATH%" ^
  -ngl 28 ^
  -c 20480 ^
  --parallel 1 ^
  --threads 8 ^
  -b 1024 ^
  -ub 512 ^
  --cache-type-k q8_0 ^
  --cache-type-v q8_0 ^
  --no-warmup ^
  --temp 0.2 ^
  --top-k 80 ^
  --top-p 0.9 ^
  --min-p 0.0 ^
  --repeat-penalty 1.05 ^
  --alias lfm2

echo llama-server.exe starting in background on port %PORT%...
echo Wait 30-60s for model to load, then test: curl http://127.0.0.1:%PORT%/health
pause
