#!/bin/bash
# Qwen3-Coder-Next UD-Q4_K_XL 启动脚本（端口 8085）

MODEL_PATH="/home/jianzengliang/Models/Qwen3-Coder-Next/Qwen3-Coder-Next-UD-Q4_K_XL.gguf"
LLAMA_SERVER="/home/jianzengliang/llama.cpp/build/bin/llama-server"

# 检查模型文件是否存在
if [ ! -f "$MODEL_PATH" ]; then
    echo "错误：模型文件不存在：$MODEL_PATH"
    exit 1
fi

# 检查 llama-server 是否存在  
if [ ! -f "$LLAMA_SERVER" ]; then
    echo "错误：llama-server 不存在：$LLAMA_SERVER"
    echo "请先编译 llama.cpp："
    echo "  cd /home/jianzengliang/llama.cpp"
    echo "  cmake -B build -DGGML_CUDA=ON"
    echo "  cmake --build build --config Release"
    exit 1
fi

# 停止之前运行的 llama-server（端口 8085）
echo "停止之前运行的 llama-server (端口 8085)..."
pkill -f "llama-server.*8085" 2>/dev/null
sleep 2

# 启动 llama-server（99 层 GPU - 全 GPU 卸载）  
echo "启动 Qwen3-Coder-Next (端口 8085)..."
echo "  模型：$MODEL_PATH"
echo "  端口：8085"
echo "  上下文：262144 (256K)"
echo "  GPU 层数：99 (全 GPU 卸载)"
echo ""

$LLAMA_SERVER \
  -m "$MODEL_PATH" \
  --port 8085 \
  --ctx-size 262144 \
  --parallel 4 \
  --batch-size 512 \
  --ubatch-size 512 \
  --n-gpu-layers 99 \
  --mlock \
  --log-disable \
  > /tmp/qwen3_coder_8085.log 2>&1 &

# 保存 PID  
LLAMA_PID=$!
echo $LLAMA_PID > /tmp/qwen3_coder_8085.pid
echo "llama-server 已启动 (PID: $LLAMA_PID)"
echo "日志文件：/tmp/qwen3_coder_8085.log"

# 等待服务启动
echo "等待服务启动..."
sleep 5

# 检查服务是否启动成功
if ps -p $LLAMA_PID > /dev/null; then
    echo "✅ 服务启动成功！"
    echo "  API 端点：http://localhost:8085/v1"
    echo "  模型列表：http://localhost:8085/v1/models"
    echo ""
    echo "测试命令："
    echo "  curl http://localhost:8085/v1/models"
else
    echo "❌ 服务启动失败！"
    echo "请查看日志："
    echo "  tail -50 /tmp/qwen3_coder_8085.log"
    exit 1
fi
