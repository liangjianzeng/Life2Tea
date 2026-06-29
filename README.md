# Life2Tea

> Brew your local AI, sip by sip.

Life2Tea is a **local LLM plugin architecture system** for desktop devices.  
It enables intelligent plugin-based collaboration between language models and multimodal models running locally on your device.

## ✨ Vision

- **Plugin Interface Protocol (PIP)**: A unified interface for model and expert plugins
- **MoE-inspired Routing**: System-level Mixture-of-Experts调度 across local models
- **Resource-aware Scheduling**: Local GPU/VRAM budget management
- **Multi-end Support**: Desktop (Tauri), embedded, and multi-device sync

## 🎯 Current Features

### ✅ Core Features (v0.1.0)

#### 1. **用户认证系统**
- SQLite 数据库用户存储
- Session Cookie 认证 (life2tea_session)
- 密码安全哈希 (SHA256 + salt)
- 自动登录和登出

#### 2. **模型管理**
- 模型扫描和发现
- 模型加载/卸载控制
- **模型特定配置**:
  - GPU层数、上下文大小、线程数、批次大小
  - Flash Attention、连续批处理
  - KV 缓存类型 (F16/F32/Q4_0/Q8_0)
  - **MTP 加速配置**: 多令牌预测参数
  - 预设配置 (轻量级/平衡型/高性能)

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

#### 5. **插件系统**
- 插件扫描和加载
- 插件生命周期管理
- 插件配置持久化

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
  - 内存占用
  - 请求处理
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
  - 输入/输出 Token 计数
  - 峰值速率
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
- [ ] 高级插件开发工具
- [ ] 性能优化和缓存策略

## 📁 Project Structure

```
life2tea/
├── backend/          # Python FastAPI backend
│   └── app/         # Modular FastAPI application
│       ├── core/      # Config, Logger, Metrics
│       │   ├── config_manager.py    # Configuration management
│       │   ├── user_service.py      # User authentication
│       │   ├── api_keys_middleware.py # API key auth middleware
│       │   ├── stats_middleware.py  # Stats collection middleware 🆕
│       │   ├── log_middleware.py    # Log management middleware 🆕
│       │   └── stats_service.py     # Stats service 🆕
│       ├── plugins/   # Plugin lifecycle & model registry
│       ├── experts/   # Expert handlers (chat, tools, ...)
│       ├── routers/   # API route modules
│       │   ├── auth_router.py       # Authentication endpoints
│       │   ├── config_router.py     # Configuration endpoints
│       │   ├── model_router.py      # Model management endpoints
│       │   ├── plugin_router.py     # Plugin endpoints
│       │   ├── api_key_router.py    # API key endpoints
│       │   └── stats_router.py      # Stats and monitoring endpoints 🆕
│       └── main.py                # Application entry point
├── frontend/         # Vue 3 + TypeScript + Vite
│   └── src/
│       ├── views/           # Page components
│       │   ├── ChatView.vue
│       │   ├── ModelsView.vue
│       │   ├── SettingsView.vue
│       │   ├── PluginsView.vue
│       │   ├── ApiKeysView.vue
│       │   └── DashboardView.vue      # System monitoring dashboard 🆕
│       ├── components/      # Reusable components
│       │   ├── DirectoryBrowser.vue    # Directory browser
│       │   ├── PathPickerModal.vue     # Path picker modal
│       │   ├── Gauge.vue               # Gauge components
│       │   ├── LineChart.vue           # Line chart component
│       │   └── LogViewer.vue           # Log viewer component
│       ├── i18n/            # Internationalization
│       ├── router.ts        # Vue Router configuration
│       ├── auth.ts          # Authentication service
│       └── App.vue          # Main application component
├── electron/         # Electron desktop shell (TBD)
├── plugins/          # Plugin directory
│   ├── models/      # Model plugins
│   └── experts/     # Expert/tool plugins
├── schema/          # PIP protocol schemas (JSON Schema)
├── docs/            # Documentation
├── rfcs/           # RFC design docs
└── config/          # Configuration files
    └── life2tea.json  # Main configuration file
```

## ⚙️ Configuration

Ports and paths are managed in `config/life2tea.json` (the single source of truth for global config). `config/life2tea.json` is git-ignored because it holds local paths; copy the template to create it:

```bash
cp config/life2tea.example.json config/life2tea.json
```

Then edit `models_dir`, `llama_backend_dir`, and ports as needed:

```json
{
  "backend_port": 3003,
  "frontend_port": 5005,
  "default_host": "127.0.0.1"
}
```

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

## 🔌 Plugin Interface Protocol (PIP)

See `schema/plugin-manifest.json` for the full plugin manifest schema.

A plugin is a directory with a `manifest.json`:

```json
{
  "name": "llama-cpp",
  "version": "1.0.0",
  "type": "model",
  "entry": "server.py",
  "description": "llama.cpp backend plugin",
  "capabilities": ["chat", "completion"],
  "resource": { "vram_mb": 4096 }
}
```

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
| `GET /api/logs` | GET | Get system logs |

### System
| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /health` | GET | Health check |
| `POST /api/chat/completions` | POST | Chat completion (SSE) |
| `GET /api/plugins` | GET | List all plugins |

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

### Models & Plugins
- **llama.cpp**: Primary backend
- **Ollama**: Alternative backend
- **vLLM**: High-performance option
- **PIP**: Plugin Interface Protocol

## 📄 License

MIT License — see LICENSE file.

## 🤝 Contributing

RFC docs are in `rfcs/`. Plugin development guide coming soon.

## 📊 Development Status

### Current Version: v0.1.0
- ✅ User authentication system
- ✅ Model management with specific configurations
- ✅ API key management
- ✅ Path picker with cross-platform support
- ✅ Plugin system
- ✅ Internationalization (zh-CN/en)
- 🆕 System monitoring dashboard
- 🆕 Log management system
- 🆕 Statistics and analytics
- 🆕 API key usage statistics

### Upcoming Features: v0.2.0
- [ ] Tauri desktop application
- [ ] Multi-device sync
- [ ] Prometheus/Grafana integration
- [ ] Cloud deployment support
- [ ] Advanced plugin development tools

---

_Migrated from LiangLLM. Reborn as Life2Tea. 🍵_
