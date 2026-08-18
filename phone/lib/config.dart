import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 连接配置：
/// - host / port 非机密，存 SharedPreferences
/// - API Key 机密，存 flutter_secure_storage（Android Keystore 加密）
class SecureConfig {
  SecureConfig._(); // 静态工具类

  static const _kHost = 'server_host';
  static const _kPort = 'server_port';
  static const _kApiKey = 'api_key';

  static const _storage = FlutterSecureStorage();

  static Future<String> host() async =>
      (await SharedPreferences.getInstance()).getString(_kHost) ?? '';

  static Future<int> port() async =>
      (await SharedPreferences.getInstance()).getInt(_kPort) ?? 3003;

  static Future<String> apiKey() async =>
      await _storage.read(key: _kApiKey) ?? '';

  static Future<bool> isConfigured() async =>
      (await host()).isNotEmpty && (await apiKey()).isNotEmpty;

  static Future<void> save({
    required String host,
    required int port,
    required String apiKey,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kHost, host.trim());
    await prefs.setInt(_kPort, port);
    await _storage.write(key: _kApiKey, value: apiKey.trim());
  }

  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kHost);
    await prefs.remove(_kPort);
    await _storage.delete(key: _kApiKey);
  }

  static String baseUrl(String host, int port) => 'http://$host:$port';
}
