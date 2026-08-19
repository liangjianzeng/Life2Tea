import 'dart:convert';

import 'package:http/http.dart' as http;

/// 只读 API 客户端 —— 仅暴露监控类 GET 接口，绝无任何写操作。
class Life2TeaApi {
  Life2TeaApi({required this.baseUrl, required this.apiKey})
      : _client = http.Client();

  final String baseUrl;
  final String apiKey;
  final http.Client _client;

  Map<String, String> get _headers => {
        'Authorization': 'Bearer $apiKey',
        'Content-Type': 'application/json',
      };

  Future<Map<String, dynamic>> _get(String path) async {
    final resp = await _client
        .get(Uri.parse('$baseUrl$path'), headers: _headers)
        .timeout(const Duration(seconds: 15));
    if (resp.statusCode == 200) {
      return jsonDecode(resp.body) as Map<String, dynamic>;
    }
    throw ApiError('HTTP ${resp.statusCode}: ${resp.body}');
  }

  /// 一次取回聚合仪表盘数据（系统负载 + 模型状态 + 网关汇总）。
  Future<Map<String, dynamic>> dashboard() => _get('/api/mobile/dashboard');

  Future<Map<String, dynamic>> systemMetrics() => _get('/api/stats/system');

  /// 资源使用历史（CPU / 内存 / GPU / 磁盘 IO），range: 1h / 6h / 24h / 7d / 30d。
  Future<Map<String, dynamic>> resourceUsage(String range) =>
      _get('/api/stats/resources?range=$range');

  Future<Map<String, dynamic>> modelMetrics() => _get('/api/stats/model-metrics');

  Future<Map<String, dynamic>> gatewaySummary() =>
      _get('/api/stats/gateway/summary?period=day');

  /// 测试连接：GET /health。
  Future<bool> health() async {
    final resp = await _client
        .get(Uri.parse('$baseUrl/health'), headers: _headers)
        .timeout(const Duration(seconds: 10));
    if (resp.statusCode == 200) {
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      return body['status'] == 'ok';
    }
    return false;
  }

  void dispose() => _client.close();
}

class ApiError implements Exception {
  ApiError(this.message);
  final String message;
  @override
  String toString() => message;
}
