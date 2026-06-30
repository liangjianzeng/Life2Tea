# Life2Tea — Linux ARM Deployment Guide

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU       | ARM v8 (aarch64) | ARM v8.2+ |
| RAM       | 8 GB   | 16 GB+ |
| Disk      | 10 GB  | 20 GB+ (for models) |
| OS        | Ubuntu 20.04+, Debian 11+ | Ubuntu 22.04 LTS |
| Python    | 3.9+   | 3.11+ |
| GPU       | None (CPU-only supported) | GPU for acceleration |

## Quick Start

```bash
# Clone repository
git clone https://github.com/your-org/Life2Tea.git
cd Life2Tea/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 3002
```

## Frontend Deployment

```bash
cd ../frontend

# Install dependencies
npm install

# Build for production
npm run build

# Serve dist/ with any static server (nginx, caddy, etc.)
# Or use dev mode for development:
npm run dev
```

## Backend Architecture (Linux ARM)

The backend is pure Python with these dependencies:

| Dependency | ARM Support | Notes |
|------------|-------------|-------|
| fastapi    | ✅ Yes      | Pure Python |
| uvicorn    | ✅ Yes      | Pure Python |
| pydantic   | ✅ Yes      | Pure Python |
| httpx      | ✅ Yes      | Pure Python |
| psutil     | ✅ Yes      | Pure Python |
| SQLAlchemy | ✅ Yes      | Pure Python |
| loguru     | ✅ Yes      | Pure Python |
| aiohttp    | ✅ Yes      | Pure Python |
| orjson     | ✅ Yes      | Pre-built wheels for aarch64 |

**No C extensions, no platform-specific code** — fully compatible with Linux ARM.

## Model Runtime (llama-server)

For LLM inference, you'll need `llama-server` compiled for ARM:

```bash
# Build llama-server for ARM (requires CMake & build tools)
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
mkdir build && cd build
cmake ..
make -j$(nproc) llama-server
```

Place the binary in `backend/backends/llama-cpp-cpu/llama-server` or specify via config.

## Configuration

Create `.env` in `backend/`:

```env
# Backend
HOST=0.0.0.0
PORT=3002
DEBUG=false

# Database
DATABASE_URL=sqlite:///backend/data/data.db

# Frontend
VITE_API_URL=http://localhost:3002
```

## Service (systemd)

Create `/etc/systemd/system/life2tea.service`:

```ini
[Unit]
Description=Life2Tea Backend
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/Life2Tea/backend
Environment="PATH=/path/to/Life2Tea/backend/venv/bin"
ExecStart=/path/to/Life2Tea/backend/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 3002
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable life2tea
sudo systemctl start life2tea
```

## Frontend Build

The frontend uses Vite + Vue 3 + TypeScript. Build produces static files:

```bash
cd frontend
npm install
npm run build
```

Output: `frontend/dist/` — serve with nginx, caddy, or any static file server.

## Troubleshooting

### `orjson` not found
```bash
pip install orjson
```
orjson provides pre-built aarch64 wheels — no compilation needed.

### `psutil` installation fails
```bash
pip install psutil
```
psutil is pure Python on Linux — no C compilation needed.

### Model binary not found
Ensure `llama-server` binary is executable:
```bash
chmod +x /path/to/llama-server
```

## Performance Tips

1. Use `gunicorn` with multiple workers for production:
   ```bash
   pip install gunicorn
   gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
   ```

2. Enable gzip compression in nginx/caddy for frontend assets.

3. For CPU inference, set `--threads` and `--batch` parameters in llama-server args.
