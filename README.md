# Life2Tea

> Brew your local AI, sip by sip.

Life2Tea is a **local LLM unified model gateway** for desktop devices.  
It aggregates multiple local inference backends (llama.cpp / vLLM / SGLang) behind a single OpenAI-compatible API, with task-based routing, fallback chains, resource-aware scheduling, and a monitoring dashboard.

## ✨ Vision

- **Unified Model Gateway**: One OpenAI-compatible entry aggregating multiple local backends
- **MoE-inspired Routing**: System-level Mixture-of-Experts scheduling across local endpoints
- **Resource-aware Scheduling**: Local GPU/VRAM budget management + LRU eviction
- **Multi-end Support**: Desktop (Tauri), embedded, and multi-device sync

## 🎯 Current Features

### ✅ Core Features (v0.1.0)

#### 1. **用户认证系统**
- SQLite 数据库用户存储
- Session Cookie 认证 (life2tea_session)
- 密码安全哈希 (SHA256 + salt)
- 自动登录和登出

#### 2. **统一模型网关**
- **OpenAI 兼容统一 API**: `/v1/chat/completions`、`/v1/completions`、`/v1/models`
- **多后端聚合**: llama.cpp (llama-server) / vLLM / SGLang，均走 OpenAI 兼容 HTTP
- **Provider 管理**: 端点声明（host/port/model/params）+ 启停 + 健康
- **任务路由 + 失败回退链**: 代码/视觉/数学/聊天分类 → 候选端点链，首选失败自动切换
- **资源预算**: VRAM/RAM 预算、LRU 逐出
- **统一流式 (SSE)**: keep-alive 心跳 + 统一错误块
- **真实 token 计量**: 写入 `token_usage`，接通 `MetricsCollector`

#### 3. **API 密钥管理**
- CRUD 操作
- 权限范围控制 (read/write/models/chat)
- 过期时间设置
- 使用统计

#### 4. **路径选择器**
- 跨平台目录浏览 (Windows/Linux)
- 智能文件识别:
  - 可执行文件 (.exe, .sh, .bat)
  - 模型文件 (.gguf, .bin, .model)
  - 配置文件 (.json, .yaml, .toml)
- 颜色编码标识

#### 5. **模型网关管理界面** (Models/Providers 视图)
- 端点列表（provider 类型/端口/状态）
- 加载/卸载、参数配置（键值编辑器，映射各后端 CLI 参数）
- 配置持久化到 `config/gateway.json`

#### 6. **国际化支持**
- 中文/英文切换
- 完整的 UI 翻译
- 路径选择器提示

#### 7. **系统监控仪表盘** 🆕
- **实时系统指标**:
  - CPU 使用率
  - 内存使用率
  - GPU 使用率
  - 网络流量
  - 磁盘使用率
- **模型状态监控**:
  - 运行状态
  - 内存占用（进程 RSS / 系统内存）
  - 请求处理
  - **模型运行指标卡片 (Token 实时统计)** 🆕
    - 一行卡片，按端口展示每个 `llama-server` 实例
    - **tok/s**：当前窗口速率 + **真实峰值**（探针每请求 `predicted_per_second`，滚动 60s 最大值，非窗口均值）
    - **MTP 接受率**：多令牌预测接受率（drafted/accepted）
    - **累计入 / 累计出**：累计 prompt token 与 generated token（取自 `prompt_tokens_total` / `predicted_tokens_total`）
    - **预填充速率**（prompt tok/s）当前值与峰值
    - 轮询 10s 刷新；峰值存于文件级 `model-metrics` 峰值存储，跨服务 reload / 多 worker 一致
- **性能图表**:
  - 请求趋势
  - Token 消耗
  - 响应时间分布

#### 8. **日志管理系统** 🆕
- **系统日志**: 路由处理信息
- **模型响应日志**: Token 消耗、生成时间
- **API 密钥日志**: 使用情况追踪
- **错误日志**: 异常和警告
- **功能特性**:
  - 实时滚动
  - 过滤搜索
  - 数据导出
  - 持久化存储

#### 9. **统计功能** 🆕
- **Token 使用统计**:
  - 输入/输出 Token 计数（累计入 / 累计出，分别取自 prompt / predicted 计数器）
  - 峰值速率（**真实峰值**：取自每请求 timings，而非窗口平均值）
  - 模型使用排行
- **资源使用统计**:
  - CPU/内存/磁盘历史趋势
  - GPU 性能分析
  - 网络带宽统计
- **API 密钥统计**:
  - 请求计数
  - 成功率/失败率
  - 响应时间分析
  - 端点使用分布
  - 异常检测
  - 告警系统

### 🔮 Planned Features (v0.2.0)

- [ ] Electron → Tauri 桌面应用
- [ ] 多设备同步
- [ ] 第三方监控集成 (Prometheus/Grafana)
- [ ] 云部署支持
- [ ] 更多 Provider 后端（Ollama/云端 API）
- [ ] 性能优化和缓存策略

## 📁 Project Structure

```
life2tea/
├── backend/          # Python FastAPI backend
│   └── app/         # Modular FastAPI application
│       ├── core/      # Config, Logger, Metrics, Stats
│       ├── gateway/   # Unified Model Gateway 🆕
│       │   ├── providers/  # Provider abstraction (llamacpp/vllm/sglang)
│       │   ├── manager.py  # ProviderManager (lifecycle/VRAM/ports)
│       │   ├── router.py   # GatewayRouter (task routing + fallback)
│       │   └── router_api.py  # OpenAI-compatible /v1 API
│       ├── routers/   # API route modules
│       │   ├── auth_router.py       # Authentication endpoints
│       │   ├── config_router.py     # Configuration endpoints
│       │   ├── models_router.py     # Model endpoint management
│       │   ├── chat_router.py       # Chat endpoints (gateway-backed)
│       │   ├── api_keys_router.py   # API key endpoints
│       │   └── stats_router.py      # Stats and monitoring endpoints 🆕
│       └── main.py                # Application entry point
├── frontend/         # Vue 3 + TypeScript + Vite
│   └── src/
│       ├── views/           # Page components
│       │   ├── ChatView.vue
│       │   ├── ModelsView.vue      # Model Gateway / Providers
│       │   ├── SettingsView.vue
│       │   ├── ApiKeysView.vue
│       │   └── DashboardView.vue      # System monitoring dashboard 🆕
│       ├── api/           # API client modules 🆕
│       ├── stores/        # Pinia stores (gateway) 🆕
│       ├── types/         # Shared TS types 🆕
│       ├── components/    # Reusable components
│       ├── i18n/          # Internationalization
│       ├── router.ts      # Vue Router configuration
│       └── App.vue        # Main application component
├── schema/          # JSON Schemas
├── docs/            # Documentation (gateway-refactor-design.md)
├── rfcs/           # RFC design docs (003-unified-gateway)
└── config/          # Configuration files
    ├── life2tea.json     # Global paths/env
    └── gateway.json      # Model gateway config (providers/routing) 🆕
```

## ⚙️ Configuration

- **`config/life2tea.json`**: global paths/env (`models_dir`, `llama_server_exe`, ports). Git-ignored; copy from `config/life2tea.example.json`.
- **`config/gateway.json`** 🆕: the **model gateway config** — `providers`, `routing` rules, `resource_budget`. Git-ignored; template at `config/gateway.example.json`.

```bash
cp config/life2tea.example.json config/life2tea.json
cp config/gateway.example.json config/gateway.json
```

A gateway provider entry:

```json
{
  "providers": {
    "lfm2": {
      "provider": "llamacpp",
      "model_path": "${MODELS_DIR}/lfm2.gguf",
      "host": "127.0.0.1",
      "port": 8082,
      "params": { "ctx_size": 32768, "n_gpu_layers": 99 }
    },
    "qwen3.6": { "provider": "vllm", "model_name": "Qwen/Qwen3-6B", "port": 8083 }
  }
}
```

DB path is resolved from `LIFE2TEA_DB` / `DATABASE_URL` env, else `config/life2tea.db`.

Frontend proxy target is in `frontend/.env.development`:
```
VITE_BACKEND_URL=http://127.0.0.1:3003
VITE_FRONTEND_PORT=5005
```

> **Changing ports**: Update `backend_port` in `config/life2tea.json` and `VITE_BACKEND_URL` in `frontend/.env.development`, then restart both services.

---

## 🚀 Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m app.main
# Server starts at http://127.0.0.1:3003
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Vite dev server at http://localhost:5005
```

## 🔌 Unified Model Gateway (OpenAI 兼容)

External applications call the gateway as a standard OpenAI-compatible API:

```
POST /v1/chat/completions   # 聊天补全（SSE 流式或 JSON）
POST /v1/completions        # 文本补全
GET  /v1/models             # 列出已配置端点
POST /v1/models/{name}/load | /v1/models/{name}/unload
GET  /v1/models/{name}      # 端点详情
GET  /health                # 网关健康
```

网关根据 `model` 字段或消息内容做任务路由，并按候选链失败回退。鉴权中间件默认关闭（按需启用）。

详见 `docs/gateway-refactor-design.md` 与 `rfcs/003-unified-gateway.md`。

## 📖 API Endpoints

### Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /api/auth/login` | POST | Login with email/password |
| `POST /api/auth/logout` | POST | Logout and invalidate session |
| `GET /api/auth/check` | GET | Check authentication status |

### Configuration
| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/config/global` | GET | Get global configuration |
| `POST /api/config/global` | POST | Save global configuration |
| `GET /api/config/model/{family}` | GET | Get model-specific configuration |
| `POST /api/config/model/{family}` | POST | Save model-specific configuration |

### Models
| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /api/models/scan` | POST | Scan for available models |
| `GET /api/models` | GET | List discovered models |
| `POST /api/models/{family}/load` | POST | Load a model |
| `POST /api/models/{family}/unload` | POST | Unload a model |

### API Keys
| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/keys` | GET | List API keys |
| `POST /api/keys` | POST | Create new API key |
| `DELETE /api/keys/{id}` | DELETE | Delete API key |
| `GET /api/keys/stats` | GET | Get API key usage statistics |

### Monitoring & Statistics 🆕
| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/stats/dashboard` | GET | Get dashboard statistics |
| `GET /api/stats/resources` | GET | Get resource usage statistics |
| `GET /api/stats/performance` | GET | Get performance statistics |
| `GET /api/stats/api-keys` | GET | Get API key usage statistics |
| `GET /api/stats/model-metrics` | GET | 模型运行指标 / Token 实时统计（按端口） 🆕 |
| `GET /api/logs` | GET | Get system logs |

### Gateway (OpenAI 兼容)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /v1/chat/completions` | POST | Chat completion (SSE/JSON) |
| `POST /v1/completions` | POST | Text completion |
| `GET /v1/models` | GET | List endpoints |
| `POST /v1/models/{name}/load` | POST | Load endpoint |
| `POST /v1/models/{name}/unload` | POST | Unload endpoint |
| `GET /health` | GET | Health check |

### Chat (内部)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /api/chat/completions` | POST | Chat completion (SSE) |
| `PUT /api/chat/conversation/{id}` | PUT | Update conversation title/model |

## 🛠️ Tech Stack

### Backend
- **Python**: 3.10+
- **Framework**: FastAPI / Uvicorn
- **Database**: SQLite (users, sessions, API keys, stats)
- **Auth**: Session cookies + Bearer API keys
- **Monitoring**: psutil, nvidia-smi, system metrics

### Frontend
- **Vue**: 3.x with Composition API
- **TypeScript**: Full type safety
- **Build**: Vite
- **Routing**: Vue Router
- **State**: Reactive refs
- **Charts**: ECharts
- **i18n**: vue-i18n

### Desktop (Planned)
- **Tauri**: Cross-platform desktop app
- **Electron**: Legacy support

### Models & Gateway
- **llama.cpp (llama-server)**: Local GGUF backend
- **vLLM**: High-performance OpenAI-compatible backend
- **SGLang**: Alternative high-performance backend
- **Unified Gateway**: Provider abstraction + routing + fallback + VRAM budget

## 📄 License

MIT License — see LICENSE file.

## 🤝 Contributing

RFC docs are in `rfcs/` (see `003-unified-gateway.md`). Provider development guide coming soon.

## 📊 Development Status

### Current Version: v0.2.0
- ✅ Unified Model Gateway (Provider abstraction / routing / fallback / /v1 API)
- ✅ User authentication system (disabled by default)
- ✅ Model gateway management UI (Models/Providers view)
- ✅ API key management
- ✅ Path picker with cross-platform support
- ✅ Internationalization (zh-CN/en)
- 🆕 System monitoring dashboard
- 🆕 Log management system
- 🆕 Statistics and analytics
- 🆕 API key usage statistics
- 🆕 模型运行指标 / Token 实时统计（真实峰值 tok/s、MTP 接受率、累计入/出）

### Upcoming Features: v0.2.0
- [ ] Tauri desktop application
- [ ] Multi-device sync
- [ ] Prometheus/Grafana integration
- [ ] Cloud deployment support
- [ ] More Provider backends (Ollama / cloud APIs)

---

_Migrated from LiangLLM. Reborn as Life2Tea. 🍵_
