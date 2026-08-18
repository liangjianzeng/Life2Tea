import 'dart:async';

import 'package:flutter/material.dart';

import 'api.dart';
import 'config.dart';

/// 仪表盘：系统负载 + 模型运行状态，每 10s 轮询聚合接口。
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Life2TeaApi? _api;
  Timer? _timer;

  bool _loading = true;
  bool _connected = false;
  String? _error;
  String? _updatedAt;
  Map<String, dynamic>? _system;
  List<dynamic> _servers = [];
  int _runningCount = 0;

  @override
  void initState() {
    super.initState();
    _connect();
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _api?.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    final host = await SecureConfig.host();
    final port = await SecureConfig.port();
    final key = await SecureConfig.apiKey();
    if (!mounted) return;
    setState(() {
      _api = Life2TeaApi(
        baseUrl: SecureConfig.baseUrl(host, port),
        apiKey: key,
      );
    });
    await _refresh();
  }

  Future<void> _refresh() async {
    final api = _api;
    if (api == null) return;
    try {
      final data = await api.dashboard();
      if (!mounted) return;
      setState(() {
        _connected = true;
        _loading = false;
        _error = null;
        _updatedAt = data['updated_at'] as String?;
        _system = data['system'] as Map<String, dynamic>?;

        final mm = data['model_metrics'] as Map<String, dynamic>?;
        final mmData = mm?['data'] as Map<String, dynamic>?;
        _servers = mmData?['servers'] as List<dynamic>? ?? [];

        final gw = data['gateway'] as Map<String, dynamic>?;
        _runningCount = (gw?['running'] as List<dynamic>? ?? []).length;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _connected = false;
        _loading = false;
        _error = '$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (_loading && _system == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null && _system == null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off, size: 48, color: Colors.redAccent),
              const SizedBox(height: 12),
              Text('无法连接服务器', style: theme.textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(_error!, style: theme.textTheme.bodyMedium),
              const SizedBox(height: 16),
              FilledButton(onPressed: _connect, child: const Text('重试')),
            ],
          ),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _ConnectionHeader(
            connected: _connected,
            running: _runningCount,
            updated: _updatedAt,
          ),
          const SizedBox(height: 16),

          // ── 系统负载 ──
          Text('系统负载', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          _SystemLoadGrid(system: _system),

          const SizedBox(height: 16),

          // ── 模型状态 ──
          Text('模型运行状态 (${_servers.length})', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          if (_servers.isEmpty)
            Text('未发现运行中的模型服务器', style: theme.textTheme.bodyMedium)
          else
            ..._servers.map((s) => _ServerCard(server: s as Map<String, dynamic>)),
        ],
      ),
    );
  }
}

class _ConnectionHeader extends StatelessWidget {
  const _ConnectionHeader({
    required this.connected,
    required this.running,
    this.updated,
  });

  final bool connected;
  final int running;
  final String? updated;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Text(
              connected ? '● 已连接' : '○ 已断开',
              style: theme.textTheme.labelLarge?.copyWith(
                color: connected ? Colors.greenAccent : Colors.redAccent,
              ),
            ),
            const Spacer(),
            Text('运行中模型: $running', style: theme.textTheme.labelLarge),
            if (updated != null) ...[
              const SizedBox(width: 8),
              Text('更新于 $updated',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.hintColor,
                  )),
            ],
          ],
        ),
      ),
    );
  }
}

class _SystemLoadGrid extends StatelessWidget {
  const _SystemLoadGrid({this.system});

  final Map<String, dynamic>? system;

  @override
  Widget build(BuildContext context) {
    if (system == null) return const Text('--');
    final mem = system!['memory'] as Map<String, dynamic>?;
    final disk = system!['disk'] as Map<String, dynamic>?;
    final gpu = system!['gpu'] as Map<String, dynamic>?;
    final net = system!['network'] as Map<String, dynamic>?;

    return Column(
      children: [
        Row(
          children: [
            Expanded(child: _MetricCard('CPU', _fmt(system!['cpu']), '%')),
            const SizedBox(width: 8),
            Expanded(child: _MetricCard('内存', _fmt(mem?['percent']), '%')),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(child: _MetricCard('磁盘', _fmt(disk?['percent']), '%')),
            const SizedBox(width: 8),
            Expanded(
              child: _MetricCard(
                'GPU',
                _fmt(gpu?['utilization']),
                '%',
                subtitle: gpu?['temperature_c'] != null
                    ? '${gpu!['temperature_c']}°C'
                    : null,
              ),
            ),
          ],
        ),
        if (net != null) ...[
          const SizedBox(height: 8),
          _MetricCard(
            '网络',
            null,
            '',
            subtitle: '↓ ${_fmtRate(net['rate_recv'])}  ↑ ${_fmtRate(net['rate_sent'])}',
          ),
        ],
      ],
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard(this.label, this.value, this.suffix, {this.subtitle});

  final String label;
  final String? value;
  final String suffix;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: theme.textTheme.labelLarge?.copyWith(color: theme.hintColor)),
            Text('${value ?? '--'}$suffix', style: theme.textTheme.titleLarge),
            if (subtitle != null)
              Text(subtitle!,
                  style: theme.textTheme.labelSmall?.copyWith(color: theme.hintColor)),
          ],
        ),
      ),
    );
  }
}

class _ServerCard extends StatelessWidget {
  const _ServerCard({required this.server});

  final Map<String, dynamic> server;

  String _fmtNum(String k) => _fmt(server[k]) ?? '--';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final model = server['model']?.toString() ?? '模型';
    final alive = (server['alive'] as bool?) ?? true;
    final spec = server['spec'] as Map<String, dynamic>?;
    final mtp = server['mtp'] as Map<String, dynamic>?;
    final mtpOn = mtp?['enabled'] as bool? ?? false;

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(model, style: theme.textTheme.titleMedium),
                ),
                Text(
                  alive ? '运行中' : '异常',
                  style: theme.textTheme.labelLarge?.copyWith(
                    color: alive ? Colors.greenAccent : Colors.redAccent,
                  ),
                ),
              ],
            ),
            Text('端口 ${server['port']} · PID ${server['pid']}',
                style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 16,
              runSpacing: 8,
              children: [
                _Stat('tok/s', _fmtNum('tok_s')),
                _Stat('峰值', _fmtNum('tok_s_peak')),
                _Stat('日峰', _fmtNum('tok_s_peak_day')),
                _Stat('预填充', _fmtNum('prompt_tok_s')),
                _Stat('入/出', '${server['total_prompt_tokens'] ?? 0}/${server['total_predicted_tokens'] ?? 0}'),
                if (spec?['label'] != null) _Stat('投机', spec!['label'].toString()),
              ],
            ),
            if (mtpOn) ...[
              const SizedBox(height: 8),
              Text(
                'MTP 接受率: ${mtp?['acceptance'] != null ? '${(mtp!['acceptance'] * 100).toInt()}%' : '--'} '
                '(drafted ${mtp?['drafted'] ?? 0} / accepted ${mtp?['accepted'] ?? 0})',
                style: theme.textTheme.bodySmall?.copyWith(color: Colors.amber),
              ),
            ],
            if (server['error'] != null)
              Text('${server['error']}',
                  style: theme.textTheme.bodySmall?.copyWith(color: Colors.redAccent)),
          ],
        ),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: theme.textTheme.labelSmall?.copyWith(color: theme.hintColor)),
        Text(value, style: theme.textTheme.titleSmall),
      ],
    );
  }
}

// ── 格式化助手 ──
String? _fmt(Object? v) {
  if (v == null) return null;
  if (v is num) {
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(1)}k';
    return v.toStringAsFixed(1);
  }
  return v.toString();
}

String _fmtRate(Object? v) {
  final f = _fmt(v);
  return f == null ? '--' : '$f/s';
}
