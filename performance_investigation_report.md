# Qwen3.6-27B llama.cpp 性能问题排查报告

## 📋 执行概要

**测试日期**: 2026-06-28  
**测试环境**: DGX Spark (GB10) / 128GB 统一内存 / llama.cpp b9829  
**测试模型**: Qwen3.6-27B-Q4_K_M-mtp.gguf (16.8 GB)

---

## 🔍 问题 1: 为什么这么慢？

### 测试结果

| 配置 | 速度 (tok/s) | TTFT (ms) | 备注 |
|------|----------------|-------------|------|
| llama.cpp (禁用 MTP) | 11.7 | 145 | 基准 |
| llama.cpp (启用 MTP) | 9.4 | 133 | MTP 反而更慢 |
| vLLM (Qwen3.6-35B-A3B) | 52.2 | 70 | MoE 架构优势 |

**结论**: llama.cpp + Qwen3.6-27B 的速度确实是 **~12 tok/s**，这是预期的。

### 为什么这么慢？

#### 1. 模型规模大
- **27B 参数** (稠密模型)
- 每次前向传播要计算**全部 27B 参数**
- Q4_K_M 量化 ≈ 16.8 GB 模型大小

#### 2. 内存带宽瓶颈
- GB10 的 LPDDR5X 带宽 ≈ **273 GB/s**
- 每个 token 需要加载 ~16GB 模型数据
- 理论速度上限 ≈ 273 GB/s / 16GB ≈ **17 tok/s**
- 实际 ~12 tok/s，接近理论上限的 70%

#### 3. GPU 计算能力
- GB10 GPU 的计算能力可能不如专业 GPU (如 H100)
- `nvidia-smi dmon` 显示推理时 GPU 利用率 96%，说明**计算密集型**

#### 4. 对比：vLLM 为什么快？
- **MoE 架构**: Qwen3.6-35B-A3B 每次只激活 **3B 参数** (11%)
- **计算量减少 9 倍** → 速度提升 4.4 倍
- **vLLM 优化**: PagedAttention, Continuous Batching, FlashAttention

---

## 🔍 问题 2: 为什么 MTP 加速没用？

### 测试结果

| 配置 | 速度 (tok/s) | 差异 |
|------|----------------|------|
| 禁用 MTP | 11.8 | 基准 |
| 启用 MTP (--spec-draft-n-max 2) | 9.4 | **慢 20%** |

**结论**: MTP **不仅没加速，反而更慢**！

### 为什么 MTP 没用？

#### 可能原因 1: 模型不是真正的 MTP 模型
- 文件名 `Qwen3.6-27B-Q4_K_M-mtp.gguf` 带 "mtp" 后缀
- 但 **llama.cpp 的 MTP 需要模型在训练时特殊设计**
- 普通模型 + `--spec-type draft-mtp` 可能**不生效或效率低下**

**验证方法**:
```bash
# 检查模型是否真的支持 MTP
/home/jianzengliang/llama.cpp/build/bin/llama-cli \
    -m Qwen3.6-27B-Q4_K_M-mtp.gguf \
    --prompt "Hi" -n 10 \
    --spec-type draft-mtp --spec-draft-n-max 2 \
    2>&1 | grep -i "mtp\|spec\|draft"
```

#### 可能原因 2: llama.cpp 的 MTP 实现不成熟
- MTP (Multi-Token Prediction) 是 **llama.cpp 较新的功能**
- 可能还有 bug 或性能问题
- 需要特定模型架构才有效

#### 可能原因 3: MTP 开销大于收益
- MTP 推测解码需要**额外计算**来推测未来 token
- 如果推测**命中率低**，反而增加计算量
- 对于 27B 大模型，额外开销可能超过收益

---

## 💡 解决方案与建议

### 方案 1: 使用 MoE 模型 + vLLM（推荐）
✅ **最快方案**，速度提升 **4.4 倍**

**步骤**:
1. 使用 Qwen3.6-35B-A3B 或类似 MoE 模型
2. 用 vLLM 作为推理引擎（已在端口 8100 运行）
3. 集成到 Life2Tea

**命令**:
```bash
vllm serve /home/jianzengliang/Models/Qwen3.6-35B-A3B-FP8 \
    --port 8100 \
    --host 0.0.0.0 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 8192 \
    --trust-remote-code
```

### 方案 2: 使用更小的稠密模型
✅ **平衡方案**，速度更快，精度略降

**推荐模型**:
- Qwen3.6-14B-Q4_K_M (≈ 8.9 GB) → 预计速度 ~25 tok/s
- Qwen3.6-8B-Q4_K_M (≈ 5.1 GB) → 预计速度 ~40 tok/s

### 方案 3: 使用更激进的量化
⚠️ **会损失精度**

- Q3_K_M → 模型大小减少到 ~12 GB
- Q2_K → 模型大小减少到 ~9 GB
- 速度提升，但精度下降

### 方案 4: 正确的 MTP 使用（如果可用）
🔬 **需要真正的 MTP 模型**

- 从 HuggingFace 下载**官方支持 MTP 的模型**
- 或使用 llama.cpp 的 `convert-hf-to-gguf.py` 转换支持 MTP 的模型
- 参考 llama.cpp 的 MTP 文档

---

## 📊 性能对比总结

| 方案 | 速度 (tok/s) | TTFT (ms) | 优点 | 缺点 |
|------|----------------|-------------|------|------|
| llama.cpp + 27B | 11.7 | 145 | 易用 | 太慢 |
| vLLM + MoE 35B | 52.2 | 70 | **最快** | 需要 vLLM |
| llama.cpp + 14B | ~25 | ~80 | 平衡 | 精度略降 |
| llama.cpp + 8B | ~40 | ~50 | 很快 | 精度下降 |

---

## 🎯 推荐配置

### 当前最优方案
```bash
# 使用 vLLM + MoE 模型
vllm serve Qwen3.6-35B-A3B-FP8 \
    --port 8100 \
    --gpu-memory-utilization 0.85
```

### 如果要继续用 llama.cpp
```bash
# 使用更小的模型
/home/jianzengliang/llama.cpp/build/bin/llama-server \
    --model Qwen3.6-14B-Q4_K_M.gguf \
    --port 8088 \
    --ctx-size 4096 \
    --n-gpu-layers -1 \
    -t 16 \
    --flash-attn on
```

---

## 📝 后续行动

1. **集成 vLLM 到 Life2Tea**
   - 添加 vLLM backend
   - 配置模型路由
   - 添加性能监控

2. **测试更多模型**
   - Qwen3.6-14B (llama.cpp)
   - Qwen3-Coder-Next (vLLM)
   - 对比速度和质量

3. **深入研究 MTP**
   - 找真正的 MTP 模型
   - 测试 llama.cpp 的 MTP 实现
   - 如果可用，速度可能提升 1.5-2x

---

## 🔧 技术细节

### GPU 利用率分析
```
推理时 GPU 利用率:
- GPU 计算 (sm): 96%  ← 计算密集型
- GPU 内存 (mem): 0%   ← GB10 统一内存，不算"GPU 内存"
```

### 内存带宽计算
```
模型大小: 16.8 GB
速度: 11.7 tok/s
带宽需求: 11.7 × 16.8 ≈ 197 GB/s
GB10 带宽: ~273 GB/s
利用率: 197/273 ≈ 72%  ← 接近上限
```

### vLLM 优势分析
```
MoE 模型: 35B 总参数，但每次只激活 3B
计算量: 减少 35/3 ≈ 12 倍
实际加速: 52.2/11.7 ≈ 4.4 倍
       (未达 12 倍因为有其他开销)
```

---

## ✅ 结论

1. **为什么慢？** → 27B 稠密模型 + 内存带宽瓶颈
2. **为什么 MTP 没用？** → 模型可能不是真正的 MTP 模型，或 llama.cpp 实现不成熟
3. **怎么解决？** → 使用 MoE 模型 + vLLM（最快），或使用更小的稠密模型

**推荐**: 在 Life2Tea 中集成 vLLM backend，使用 Qwen3.6-35B-A3B 或类似 MoE 模型。
