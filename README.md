# Life2Tea

> Brew your local AI, sip by sip.

Life2Tea is a **local LLM plugin architecture system** for desktop devices.  
It enables intelligent plugin-based collaboration between language models and multimodal models running locally on your device.

## ✨ Vision

- **Plugin Interface Protocol (PIP)**: A unified interface for model and expert plugins
- **MoE-inspired Routing**: System-level Mixture-of-Experts调度 across local models
- **Resource-aware Scheduling**: Local GPU/VRAM budget management
- **Multi-end Support**: Desktop (Tauri), embedded, and multi-device sync

## 📁 Project Structure

```
life2tea/
├── backend/          # Python FastAPI backend
│   └── app/         # Modular FastAPI application
│       ├── core/      # Config, Logger, Metrics
│       ├── plugins/   # Plugin lifecycle & model registry
│       ├── experts/   # Expert handlers (chat, tools, ...)
│       └── routers/   # API route modules
├── frontend/         # Vue 3 + TypeScript + Vite
├── electron/         # Electron desktop shell (TBD)
├── plugins/          # Plugin directory
│   ├── models/      # Model plugins
│   └── experts/     # Expert/tool plugins
├── schema/          # PIP protocol schemas (JSON Schema)
├── docs/            # Documentation
└── rfcs/           # RFC design docs
```

## 🚀 Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m app.main
# Server starts at http://127.0.0.1:3001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Vite dev server at http://localhost:5173
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

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /api/config/global` | Get global config |
| `GET /api/models` | List discovered models |
| `POST /api/models/{family}/load` | Load a model |
| `GET /api/plugins` | List all plugins |
| `POST /api/chat/completions` | Chat completion (SSE) |
| `GET /api/metrics/summary` | Performance summary |
| `POST /api/logs/query` | Query logs |

## 🛠️ Tech Stack

- **Backend**: Python 3.10+ / FastAPI / Uvicorn / httpx
- **Frontend**: Vue 3 / TypeScript / Vite / Pinia
- **Desktop**: Electron → Tauri (planned)
- **Models**: llama.cpp / Ollama / vLLM

## 📄 License

MIT License — see LICENSE file.

## 🤝 Contributing

RFC docs are in `rfcs/`. Plugin development guide coming soon.

---

_Migrated from LiangLLM. Reborn as Life2Tea. 🍵_
