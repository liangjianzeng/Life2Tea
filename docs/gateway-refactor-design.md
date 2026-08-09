# Life2Tea 统一模型网关重构设计

> 状态：已实施（Phases 0–5）· 2026-08
> 对应 RFC：`rfcs/003-unified-gateway.md`

## 1. 背景与问题

旧架构存在**三条互不共享状态的推理路径**：

1. `chat_router` + `SystemRouter` + `ChatHandler` + `PluginLifecycleManager`（主聊天路径）
2. `proxy_service` + `DynamicModelManager`（独立的 standalone_app，自管端口/LRU，不共享状态）
3. `openai_proxy.py`（死代码，从未注册）

核心问题：

- **模型路由碎片化**：`SystemRouter`（任务路由）、`ModelRouter`（/api/model-router，与聊天路径解耦）、`DynamicModelManager`（VRAM/LRU）三套并存。
- **流式不一致**：`proxy_service` 忽略 `stream=true`；只有 `chat_router/ChatHandler` 正常流式。
- **token 统计断裂**：`token_usage` 表从未写入；`MetricsCollector.record_inference` 是死代码。
- **插件体系与模型管理交织**（manifest 驱动），但插件能力薄弱，属"鸡肋"。
- **鉴权基本关闭**、跨平台硬编码路径、双 DB 文件。
- **前端无 API 层/store/共享类型**，全组件内联 fetch，无显式模型切换器。

## 2. 目标架构：统一模型网关 (Unified Model Gateway)

```
外部应用 ──> /v1/chat/completions, /v1/models (OpenAI兼容)
                    │  API-Key鉴权（按 scope，当前保持禁用）
              [ GatewayRouter ]  任务路由 + 负载均衡 + 失败回退 + VRAM预算
                    │
         [ ProviderManager ]   统一管理模型实例(子进程/外部服务)
                    │
   ┌───────────────┼───────────────┐
 LlamaCppProvider  VllmProvider   SglangProvider   (均走 OpenAI 兼容 HTTP)
      │                │               │
  llama-server       vllm serve      sglang serve
```

要点：

- **单一 OpenAI 兼容入口**：`/v1/chat/completions`、`/v1/completions`、`/v1/models`、`/v1/models/{name}`、`/v1/models/{name}/load|unload`、`/health`。
- **统一流式**：SSE + keep-alive 心跳 + 统一错误块。
- **Provider 抽象**：llamacpp / vllm / sglang 三类后端均为 OpenAI 兼容 HTTP，共享同一 client。
- **路由回退链**：首选模型失败 → 自动切换到候选模型。
- **内部仪表盘聊天路径** 复用同一 `ProviderManager`/`GatewayRouter`，仅路径不同（`/api/chat/*`）。
- **监控仪表盘完整保留**：DashboardView 现有卡片（GPU/CPU/内存/网络/磁盘/延迟/模型指标卡）不动，token 计数接通真实数据。

## 3. 代码结构

```
backend/app/gateway/
  __init__.py            # 导出 ProviderManager / GatewayRouter 等
  providers/
    base.py              # Provider 抽象 + ProviderSpec + ModelEndpoint + GatewayError
    llamacpp.py          # llama-server 启动命令构建
    vllm.py              # vLLM OpenAI server 启动命令构建
    sglang.py            # SGLang launch_server 启动命令构建
  manager.py             # ProviderManager：生命周期/端口/VRAM/LRU
  router.py              # GatewayRouter：任务分类 + 回退链 + 负载均衡
  router_api.py          # OpenAI 兼容 /v1 路由（流式 + 鉴权钩子 + telemetry）

frontend/src/
  types/index.ts         # 共享类型
  api/                   # client / chat / models API 模块
  stores/gateway.ts      # 网关 Pinia store
```

## 4. 配置

- **`config/gateway.json`**（gitignore，模板 `config/gateway.example.json`）：唯一模型配置源
  - `providers`：端点声明（provider 类型、host/port、model_path/model_name、params）
  - `routing`：任务 → 候选端点链
  - `resource_budget`：VRAM/RAM 预算、LRU 策略
  - `default_port_range` / `default_host` / `llama_server_exe` / `python`
- **`config/life2tea.json`**：全局路径/环境（models_dir、llama_server_exe），被 gateway 读取。
- **DB 路径**：`LIFE2TEA_DB` / `DATABASE_URL` 优先，默认 `config/life2tea.db`。

## 5. 分阶段实施记录

| Phase | 内容 | 提交 |
|-------|------|------|
| 0 | 同步 origin/main、清理死代码 | `171ff9a` |
| 1 | 网关核心（Provider/GatewayRouter/ProviderManager/统一 /v1 API），接入 main.py + chat_router | `febf437` |
| 2 | 彻底移除插件体系（后端 + 前端） | `4d29617` |
| 3 | 聊天修复：真实 token 计量、流式健壮、回退重试、模型切换器 | `d9a106c` |
| 4 | 前端重构：types + api + store，Models→Providers 视图，Dashboard 保留 | `139efff` |
| 5 | 配置/数据：可配置 DB 路径、消除硬编码路径；鉴权按用户选择保持禁用 | `11bb977` |

## 6. 后续待办（未实施）

- **鉴权启用**：按 scope 启用 AuthMiddleware（聊天→CHAT、模型启停→MODELS_WRITE、密钥→ADMIN）。当前按用户选择保持禁用。
- **Ollama/云端 Provider**：如需保留可新增 `OllamaProvider` / `CloudProvider`。
- **vLLM/SGLang 模型权重发现**：当前以 gateway.json 显式声明 `model_name` 为准。
- **聊天上下文长度处理**：前端可按 `ctx_size` 提示截断；网关可按 token 数拒绝超长请求。
