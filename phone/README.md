# Life2Tea-Phone

通过 VPN（如 Tailscale）远程只读监控 Life2Tea 服务器的 Android 客户端。

## 功能

- **连接设置页**：服务器地址（VPN IP）+ 端口 + `read` 权限 API Key，测试连接。
- **仪表盘页**：系统负载（CPU/内存/磁盘/网络/GPU）+ 模型运行状态（每实例 tok/s、峰值/日峰、预填充速率、MTP 接受率、投机解码类型、累计入/出 token），每 10s 轮询聚合接口。

## 架构

```
lib/
├─ main.dart           入口 + 深色主题 + 底部导航（仪表盘/设置）
├─ config.dart         连接配置（host/port → SharedPreferences；API Key → flutter_secure_storage）
├─ api.dart            只读 HTTP 客户端（仅监控类 GET，无任何写操作）
├─ dashboard_screen.dart  仪表盘
└─ setup_screen.dart   连接设置
```

## 安全设计

- **只读原则**：`api.dart` 只暴露 `api/mobile/dashboard`、`api/stats/*`、`health`，绝无 load/unload/config 写接口。
- **密钥保护**：API Key 存 `flutter_secure_storage`（Android Keystore 加密）。
- **传输**：走 VPN 加密隧道；后端 stats 路由要求 `read` scope 的 Bearer Key 才可远程访问。

## 构建

见 [BUILD.md](BUILD.md)。APK 产物输出到 `build/app/outputs/flutter-apk/`；当前版本拷贝在 `apk/Life2Tea-Phone-v0.1.0-debug.apk`。

## 配置

- 后端地址默认 `http://<VPN IP>:3003/`，在设置页填写。
- 手机端使用的只读 Key 由后端 `_issue_readonly_key.py` 签发。
