# Life2Tea 在 DGX SPARK 上部署指南

本文档介绍如何在 NVIDIA DGX SPARK 设备上部署 Life2Tea 模型管理系统。

---

## 📋 系统要求

### 硬件要求

- **GPU**: NVIDIA GPU（推荐 A100/H100，至少 24GB VRAM）
- **内存**: 64GB+ RAM
- **存储**: 100GB+ 可用空间（存放模型 GGUF 文件）
- **网络**: 10Gbps+ 网络（用于前端访问）

### 软件要求

- **操作系统**: Ubuntu 22.04 LTS / CentOS 7+
- **Python**: 3.10+
- **NVIDIA Driver**: 525+（支持 CUDA 12.x）
- **Docker** (可选): 24.0+（如需容器化部署）

---

## 📦 部署步骤

### 1. 拉取代码

```bash
cd /data
git clone <your-repo-url> Life2Tea
cd Life2Tea
```

### 2. 安装 Python 依赖

```bash
cd backend
pip install -r requirements.txt
```

依赖列表（`backend/requirements.txt`）：
```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.5.0
psutil>=5.9.0
httpx>=0.25.0
pytest>=7.4.0
```

### 3. 下载 llama.cpp 并编译 llama-server

```bash
cd /data
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp

# 编译（启用 CUDA 支持）
make clean
make LLAMA_CUDA=1 -j$(nproc)

# 验证编译
./llama-server --help
```

> **注意**: 如果不需要 GPU 加速，可以不加 `LLAMA_CUDA=1`，纯 CPU 运行。

### 4. 准备模型文件

将 GGUF 格式的模型文件放到指定目录：

```bash
mkdir -p /data/models
cp /path/to/your/*.gguf /data/models/
```

推荐模型（量化版，节省 VRAM）：
- **LFM2-24B-A2B-Q4_K_M.gguf** (推荐，~14GB VRAM)
- **Qwen3-Coder-30B-A3B-Instruct-Q3_K_M.gguf** (~14GB VRAM)
- **gemma-4-12B-it-Q4_K_M.gguf** (~7GB VRAM)

> **VRAM 占用参考**（量化 4-bit）:
> - 7B 模型: ~6GB VRAM
> - 13B 模型: ~10GB VRAM
> - 24B 模型: ~18GB VRAM
> - 30B 模型: ~22GB VRAM

### 5. 配置 Life2Tea

创建 `config/life2tea.json`：

```json
{
  "theme": "dark",
  "language": "zh-CN",
  "backend_preference": "auto",
  "backend_port": 3003,
  "frontend_port": 5005,
  "llama_backend_dir": "/data/llama.cpp",
  "llama_server_exe": "/data/llama.cpp/llama-server",
  "models_dir": "/data/models",
  "default_port_range": [8080, 8099],
  "default_host": "0.0.0.0",
  "gpu_layers": 99,
  "ctx_size": 32768,
  "threads": 16,
  "batch_size": 1024,
  "mmap": true,
  "mlock": false,
  "max_startup_wait_seconds": 300
}
```

> **配置说明**:
> - `llama_backend_dir`: llama.cpp 编译目录
> - `llama_server_exe`: llama-server 可执行文件路径
> - `models_dir`: 模型文件目录
> - `default_host`: `0.0.0.0` 允许外部访问
> - `gpu_layers`: 使用 GPU 的层数（24GB VRAM 推荐 99）
> - `ctx_size`: 上下文长度（20480-32768）
> - `threads`: CPU 线程数（根据 CPU 核心调整）

### 6. 启动后端服务

```bash
cd /data/Life2Tea/backend

# 方式 1: 直接启动（推荐测试）
uvicorn app.main:app --host 0.0.0.0 --port 3003 --reload

# 方式 2: 后台守护进程
nohup uvicorn app.main:app \
  --host 0.0.0.0 --port 3003 \
  > /data/Life2Tea/log/backend.log 2>&1 &

echo $! > /data/Life2Tea/log/backend.pid
```

检查后端是否启动成功：

```bash
curl http://localhost:3003/api/models
# 应返回模型列表
```

### 7. 启动前端服务

```bash
cd /data/Life2Tea/frontend

# 安装依赖（首次需要）
npm install

# 方式 1: 开发模式（推荐测试）
VITE_BACKEND_URL=http://<dgx-ip>:3003 npm run dev

# 方式 2: 后台守护进程
nohup sh -c "VITE_BACKEND_URL=http://<dgx-ip>:3003 npm run dev" \
  > /data/Life2Tea/log/frontend.log 2>&1 &

echo $! > /data/Life2Tea/log/frontend.pid
```

---

## 🚀 使用方式

### Web UI 访问

打开浏览器访问：
```
http://<dgx-ip>:5005
```

支持的功能：
- **Chat**: 选择模型进行对话
- **Models**: 查看/加载/卸载模型
- **Plugins**: 插件管理
- **Settings**: 系统配置

### API 调用示例

#### 1. 加载模型

```bash
curl -X POST http://<dgx-ip>:3003/api/models/lfm2/load
```

#### 2. 聊天推理（OpenAI 兼容）

```bash
curl -X POST http://<dgx-ip>:3003/api/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "你好！"}],
    "stream": false
  }'
```

#### 3. 查看当前加载的模型

```bash
curl http://<dgx-ip>:3003/api/models
```

#### 4. 卸载模型

```bash
curl -X POST http://<dgx-ip>:3003/api/models/lfm2/unload
```

---

## 🔍 故障排查

### 常见问题

#### 1. `CUDA out of memory`

**原因**: GPU VRAM 不足

**解决方案**:
- 减少 `gpu_layers`（尝试 28）
- 减小 `ctx_size`（尝试 8192）
- 使用更小的量化模型（Q3_K_M 替代 Q4_K_M）

#### 2. `llama-server not found`

**原因**: `llama_server_exe` 路径不正确

**解决方案**:
```bash
which llama-server
# 或
find /data -name "llama-server" -type f
```

更新 `config/life2tea.json` 中的路径。

#### 3. 前端无法连接后端

**原因**: CORS 或防火墙阻止

**解决方案**:
- 确保 `default_host` 是 `0.0.0.0`
- 检查防火墙端口：3003（后端）、5005（前端）
- 前端设置正确的 `VITE_BACKEND_URL`

#### 4. 模型加载超时

**原因**: 大模型加载需要更长时间

**解决方案**:
- 增加 `max_startup_wait_seconds`（尝试 600）
- 检查日志 `log/plugin_{family}.log` 查看进度

### 查看日志

```bash
# 后端日志
tail -f /data/Life2Tea/log/backend.log

# 模型启动日志
tail -f /data/Life2Tea/log/plugin_lfm2.log

# 前端日志
tail -f /data/Life2Tea/log/frontend.log
```

---

## 🛠️ 高级配置

### 多模型并发（实验性）

Life2Tea 支持同时加载多个模型（需足够 VRAM）：

```json
{
  "resource_budget": {
    "vram_mb": 24000,
    "ram_mb": 64000,
    "strategy": "evict_lru"
  }
}
```

### 使用 Docker 部署（可选）

```bash
# 后端容器
docker run -d --gpus all -p 3003:3003 \
  -v /data/models:/app/models \
  -v /data/llama.cpp:/app/llama.cpp \
  life2tea-backend

# 前端容器
docker run -d -p 5005:5005 \
  -e VITE_BACKEND_URL=http://host.docker.internal:3003 \
  life2tea-frontend
```

---

## 📊 性能参考

### DGX SPARK 典型配置

| 配置 | VRAM | 7B 模型 | 13B 模型 | 24B 模型 |
|------|------|---------|----------|----------|
| Q4_K_M | ~6GB | ~5GB | ~10GB | ~18GB |
| Q3_K_M | ~5GB | ~4GB | ~8GB | ~14GB |
| Q2_K | ~4GB | ~3GB | ~6GB | ~10GB |

### 推理性能（24B 模型，Q4_K_M）

| 配置 | Prompt TPS | Generate TPS |
|------|------------|--------------|
| 1 GPU (A100 80GB) | ~80 | ~40 |
| 1 GPU (RTX 4090 24GB) | ~30 | ~15 |

---

## 📚 参考链接

- [Life2Tea GitHub](https://github.com/liangjianzeng/Life2Tea)
- [llama.cpp](https://github.com/ggerganov/llama.cpp)
- [GGUF 模型下载](https://huggingface.co/models?search=gguf)
- [OpenAI API 兼容性](https://platform.openai.com/docs/api-reference/chat)

---

## 📞 技术支持

如有问题，请检查：
1. 日志文件中的错误信息
2. GPU 驱动版本：`nvidia-smi`
3. CUDA 版本：`nvcc --version`
4. Python 依赖版本：`pip list | grep -E "fastapi|uvicorn|psutil"`

---

**部署完成！** 🎉 现在你可以通过 Web UI 或 API 访问 Life2Tea 系统。
