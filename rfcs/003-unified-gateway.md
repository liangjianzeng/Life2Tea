# RFC 003: Unified Model Gateway

- 状态：Accepted (2026-08)
- 取代：RFC 001 (PIP plugin protocol)、RFC 002 (MoE dual mapping) 的模型层部分
- 关联实现：`docs/gateway-refactor-design.md`

## 摘要

将旧的"插件体系 + 三套并行推理路径"收敛为单一**统一模型网关**：一个 OpenAI 兼容入口聚合 llama.cpp / vLLM / SGLang 三类后端，统一流式、统一错误、统一 token 计量，并保留监控仪表盘。

## 动机

- 插件体系能力薄弱（"鸡肋"），且与模型管理（manifest）深度交织，维护成本高。
- 三条推理路径不共享状态，导致路由、流式、token 统计碎片化。
- 需要对外暴露统一、可接入外部应用的 OpenAI 兼容 API。

## 设计要点

1. **Provider 抽象**：`ProviderSpec`（声明式端点）+ 通用 OpenAI 兼容 HTTP client。
2. **ProviderManager**：子进程生命周期、端口分配、VRAM/LRU 预算。
3. **GatewayRouter**：关键字任务分类 + 显式模型偏好 + 负载均衡 + 失败回退链。
4. **统一 `/v1/*` API**：SSE 流式 + keep-alive + 统一错误块 + telemetry 钩子。
5. **移除插件体系**：删除 manifest/registry/expert/ollama_plugin 等，模型配置迁入 `config/gateway.json`。

## 取舍

- 移除插件体系即移除 Ollama 支持（如需可另作 Provider）。
- `proxy_service` 外部路径与内部聊天路径合并为一，需回归验证 OpenAI 兼容性。
- 鉴权默认保持禁用（按用户选择），启用作为后续待办。
