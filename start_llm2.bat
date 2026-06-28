@echo off
REM ============================================================
REM  start_llm2.bat - Manual fallback to launch a llama-server
REM  instance for a model. Run this only if the backend cannot
REM  start the process itself.
REM
REM  All paths can be overridden via environment variables, e.g.
REM    set LLAMA_EXE=C:\path\to\llama-server.exe
REM    set MODEL_PATH=C:\path\to\model.gguf
REM    set PORT=8082
REM  Defaults below assume a single lfm2 model on port 8082.
REM ============================================================

if "%LLAMA_EXE%"==""   set "LLAMA_EXE=D:\MyLLM\llama.cpp\llama-server.exe"
if "%MODEL_PATH%"==""  set "MODEL_PATH=D:\MyLLM\models\LFM2-24B-A2B-Q4_K_M.gguf"
if "%PORT%"==""        set "PORT=8082"
if "%NGL%"==""         set "NGL=28"
if "%CTX%"==""         set "CTX=20480"
if "%THREADS%"==""     set "THREADS=8"

echo Starting llama-server.exe on port %PORT%...
echo   EXE:   %LLAMA_EXE%
echo   Model: %MODEL_PATH%
echo   NGL=%NGL% CTX=%CTX% Threads=%THREADS%

start "Life2Tea-llm2" /B "%LLAMA_EXE%" ^
  --port %PORT% ^
  --model "%MODEL_PATH%" ^
  -ngl %NGL% ^
  -c %CTX% ^
  --parallel 1 ^
  --threads %THREADS% ^
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

echo.
echo llama-server.exe starting in background on port %PORT%.
echo Wait 30-60s for the model to load, then test:
echo   curl http://127.0.0.1:%PORT%/health
pause
