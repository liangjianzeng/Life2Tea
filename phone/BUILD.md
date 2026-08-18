# Life2Tea-Phone 构建说明

## 环境

- Flutter 不在 PATH，需全路径调用：`/home/jianzengliang/flutter/bin/flutter`
- Android SDK：`/home/jianzengliang/android-sdk`（见 `android/local.properties`）

## 本机（ARM64 / DGX Spark）构建注意

- **release 构建在此 ARM 机不可用**：Flutter release 的 AOT 快照器在 QEMU 下会
  SIGSEGV（`Dart snapshot generator failed with exit code -11`）。请改用 **debug** 构建：
  ```bash
  ANDROID_HOME=/home/jianzengliang/android-sdk /home/jianzengliang/flutter/bin/flutter build apk --debug
  # 产物: build/app/outputs/flutter-apk/app-debug.apk
  ```
- 如需 release 小体积 APK，请在有 x86/Windows Flutter 工具链的机器上构建
  （参照 DSH-Phone 的 Windows 流程，并配置 `android/key.properties` 签名）。

## 关键 Gradle 配置（android/app/build.gradle.kts）

- `ndkVersion = "27.0.12077973"`（flutter_secure_storage / shared_preferences_android 要求）
- `minSdk = 23`（flutter_secure_storage 10.x 要求）
- `abiFilters = ["arm64-v8a"]`（仅 64 位，跳过 32 位原生库编译）

## 构建步骤

```bash
cd phone
/home/jianzengliang/flutter/bin/flutter pub get
/home/jianzengliang/flutter/bin/flutter analyze
/home/jianzengliang/flutter/bin/flutter build apk --debug
# 拷贝到 apk/ 目录并命名
# cp build/app/outputs/flutter-apk/app-debug.apk apk/Life2Tea-Phone-v0.1.0-debug.apk
```

## 版本记录

- **v0.1.0**：首个发布版 —— VPN 只读监控：连接设置（地址/端口/read Key + 测试连接）+ 仪表盘（系统负载 + 模型运行状态，10s 轮询聚合接口）。
