#!/bin/bash
# Qwen3.5-4B 视觉模型启动脚本（端口 8085）
# 带视觉编码器 (--mmproj)，供网关视觉通道 / 自动兜底使用。
# 与 vv4flash 共存：模型仅 ~3.4G，小上下文省内存。

MODEL_DIR="/home/jianzengliang/Models/Qwen3.5-4B-GGUF"
MODEL_PATH="$MODEL_DIR/Qwen3.5-4B-UD-Q4_K_XL.gguf"
MMPROJ_PATH="$MODEL_DIR/mmproj-F16.gguf"
LLAMA_SERVER="/home/jianzengliang/llama.cpp/build/bin/llama-server"
PORT=8085

# 检查文件
if [ ! -f "$MODEL_PATH" ]; then
    echo "错误：主模型不存在：$MODEL_PATH"
    exit 1
fi
if [ ! -f "$MMPROJ_PATH" ]; then
    echo "错误：视觉编码器不存在：$MMPROJ_PATH"
    exit 1
fi
if [ ! -f "$LLAMA_SERVER" ]; then
    echo "错误：llama-server 不存在：$LLAMA_SERVER"
    exit 1
fi

# 停止旧的视觉服务
echo "停止旧的视觉服务 (端口 $PORT)..."
pkill -f "llama-server.*$PORT" 2>/dev/null
sleep 2

echo "启动 Qwen3.5-4B 视觉模型 (端口 $PORT)..."
echo "  模型：$MODEL_PATH"
echo "  mmproj：$MMPROJ_PATH"

$LLAMA_SERVER \
  -m "$MODEL_PATH" \
  --mmproj "$MMPROJ_PATH" \
  --port $PORT \
  --host 0.0.0.0 \
  --ctx-size 16384 \
  --parallel 1 \
  --batch-size 512 \
  --ubatch-size 512 \
  --n-gpu-layers 99 \
  --flash-attn on \
  --jinja \
  --log-disable \
  > /tmp/qwen35_vision_8085.log 2>&1 &

LLAMA_PID=$!
echo $LLAMA_PID > /tmp/qwen35_vision_8085.pid
echo "已启动 (PID: $LLAMA_PID)"
echo "日志：/tmp/qwen35_vision_8085.log"

sleep 5
if ps -p $LLAMA_PID > /dev/null; then
    echo "✅ 视觉服务启动成功"
    echo "  端点：http://localhost:$PORT/v1"
    curl -s http://localhost:$PORT/v1/models | python3 -m json.tool | head -20
else
    echo "❌ 启动失败，日志："
    tail -40 /tmp/qwen35_vision_8085.log
    exit 1
fi
