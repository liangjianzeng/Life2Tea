import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'api.dart';
import 'config.dart';

/// 仪表盘：系统负载 + 资源历史 + 模型运行状态，每 10s 轮询聚合接口。
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
  int _providers = 0;

  // 资源使用历史
  String _historyRange = '1h';
  List<dynamic> _history = [];
  bool _historyLoading = false;

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
    await _refreshHistory();
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
        _providers = (gw?['providers'] as num?)?.toInt() ?? 0;
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

  Future<void> _refreshHistory() async {
    final api = _api;
    if (api == null) return;
    try {
      final data = await api.resourceUsage(_historyRange);
      if (!mounted) return;
      setState(() {
        _historyLoading = false;
        final list = data['data'] as List<dynamic>? ?? [];
        // 只保留最近 60 个点，避免图表过密。
        _history = list.length > 60 ? list.sublist(list.length - 60) : list;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _historyLoading = false);
    }
  }

  void _setRange(String range) {
    if (_historyRange == range) return;
    setState(() {
      _historyRange = range;
      _historyLoading = true;
    });
    _refreshHistory();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (_loading && _system == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null && _system == null) {
      return _ErrorView(error: _error!, onRetry: _connect);
    }
    return RefreshIndicator(
      onRefresh: () async {
        await _refresh();
        await _refreshHistory();
      },
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          // ── 状态行 ──
          Row(
            children: [
              _ConnectionChip(connected: _connected),
              const Spacer(),
              if (_updatedAt != null)
                Text(
                  _parseTime(_updatedAt!),
                  style: theme.textTheme.labelSmall?.copyWith(color: const Color(0xFF8888AA)),
                ),
            ],
          ),
          const SizedBox(height: 8),
          // ── 概览条 ──
          _OverviewBar(
            running: _runningCount,
            providers: _providers,
          ),
          const SizedBox(height: 16),

          // ── 系统负载 ──
          _SectionTitle('系统负载'),
          const SizedBox(height: 8),
          _SystemLoadGrid(system: _system),

          const SizedBox(height: 16),

          // ── 资源使用历史 ──
          Row(
            children: [
              const _SectionTitle('资源使用历史'),
              const Spacer(),
              _RangeSelector(value: _historyRange, onChanged: _setRange),
            ],
          ),
          const SizedBox(height: 8),
          _UsageHistorySection(
            loading: _historyLoading,
            history: _history,
          ),

          const SizedBox(height: 16),

          // ── 模型状态 ──
          _SectionTitle('模型运行状态 (${_servers.length})'),
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

// ──────────────────────────────────────────────────────────────────────────
// 概览条
// ──────────────────────────────────────────────────────────────────────────
class _ConnectionChip extends StatelessWidget {
  const _ConnectionChip({required this.connected});
  final bool connected;

  @override
  Widget build(BuildContext context) {
    final color = connected ? const Color(0xFF3DDC97) : const Color(0xFFE74C3C);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(connected ? '已连接' : '已断开',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(color: color)),
        ],
      ),
    );
  }
}

class _OverviewBar extends StatelessWidget {
  const _OverviewBar({
    required this.running,
    required this.providers,
  });

  final int running;
  final int providers;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF1A1A2E), Color(0xFF23233F)],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF2D2D4A)),
      ),
      child: Row(
        children: [
          _OverviewStat(icon: Icons.model_training, value: '$running', label: '运行模型'),
          const SizedBox(width: 20),
          _OverviewStat(icon: Icons.dns, value: '$providers', label: '模型服务'),
          const Spacer(),
          const Icon(Icons.bolt, color: Color(0xFFF5B942), size: 20),
        ],
      ),
    );
  }
}

class _OverviewStat extends StatelessWidget {
  const _OverviewStat({
    required this.icon,
    required this.value,
    required this.label,
  });

  final IconData icon;
  final String value;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: const Color(0xFF7C5CFF), size: 20),
        const SizedBox(width: 8),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(value, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
            Text(label, style: Theme.of(context).textTheme.labelSmall?.copyWith(color: const Color(0xFF8888AA))),
          ],
        ),
      ],
    );
  }
}

// ──────────────────────────────────────────────────────────────────────────
// 系统负载
// ──────────────────────────────────────────────────────────────────────────
class _SystemLoadGrid extends StatelessWidget {
  const _SystemLoadGrid({this.system});

  final Map<String, dynamic>? system;

  @override
  Widget build(BuildContext context) {
    if (system == null) {
      return const Text('--');
    }
    final mem = system!['memory'] as Map<String, dynamic>?;
    final disk = system!['disk'] as Map<String, dynamic>?;
    final gpu = system!['gpu'] as Map<String, dynamic>?;
    final net = system!['network'] as Map<String, dynamic>?;

    final cpu = _asNum(system!['cpu']);
    // 与 Web 一致：内存占比取整显示
    final memPct = _asNum(mem?['percent'])?.roundToDouble();
    final diskPct = _asNum(disk?['percent']);
    final gpuPct = _asNum(gpu?['utilization']);

    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: _MetricTile(
                icon: Icons.speed,
                label: 'CPU',
                value: cpu,
                suffix: '%',
                color: _usageColor(cpu),
                subtitle: cpu == null ? null : '${cpu.toStringAsFixed(1)}%',
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _MetricTile(
                icon: Icons.memory,
                label: '内存',
                value: memPct,
                suffix: '%',
                color: _usageColor(memPct),
                subtitle: mem != null ? '${_fmtBytes(mem['used'])} / ${_fmtBytes(mem['total'])}' : null,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _MetricTile(
                icon: Icons.storage,
                label: '磁盘',
                value: diskPct,
                suffix: '%',
                color: _usageColor(diskPct),
                subtitle: disk != null ? '${_fmtBytes(disk['used'])} / ${_fmtBytes(disk['total'])}' : null,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _MetricTile(
                icon: Icons.memory,
                label: 'GPU',
                value: gpuPct,
                suffix: '%',
                color: _usageColor(gpuPct),
                subtitle: gpu?['temperature_c'] != null
                    ? '${gpu!['temperature_c']}°C · ${_fmtBytes(gpu['memory_used'])}/${_fmtBytes(gpu['memory_total'])}'
                    : '未检测到',
              ),
            ),
          ],
        ),
        if (net != null) ...[
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: _tileDecoration(),
            child: Row(
              children: [
                Icon(Icons.swap_vert, color: const Color(0xFF2EC4DE), size: 20),
                const SizedBox(width: 10),
                Text('网络', style: Theme.of(context).textTheme.labelLarge),
                const Spacer(),
                Text('↓ ${_fmtRate(net['rate_recv'])}  ↑ ${_fmtRate(net['rate_sent'])}',
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(color: const Color(0xFF8888AA))),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.icon,
    required this.label,
    required this.value,
    required this.suffix,
    required this.color,
    this.subtitle,
  });

  final IconData icon;
  final String label;
  final double? value;
  final String suffix;
  final Color color;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: _tileDecoration(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: color, size: 18),
              const SizedBox(width: 6),
              Text(label, style: theme.textTheme.labelMedium?.copyWith(color: const Color(0xFF8888AA))),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(
                _displayValue(value),
                style: theme.textTheme.headlineSmall?.copyWith(color: color, fontWeight: FontWeight.bold),
              ),
              Text(suffix, style: theme.textTheme.titleMedium?.copyWith(color: color)),
            ],
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 4),
            Text(
              subtitle!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.labelSmall?.copyWith(color: const Color(0xFF8888AA)),
            ),
          ],
        ],
      ),
    );
  }
}

// ──────────────────────────────────────────────────────────────────────────
// 资源使用历史
// ──────────────────────────────────────────────────────────────────────────
class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(title,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: const Color(0xFFE0E0FF),
            ));
  }
}

class _RangeSelector extends StatelessWidget {
  const _RangeSelector({required this.value, required this.onChanged});

  final String value;
  final ValueChanged<String> onChanged;

  static const _ranges = [
    ('1h', '1H'),
    ('6h', '6H'),
    ('24h', '24H'),
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A2E),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF2D2D4A)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < _ranges.length; i++)
            GestureDetector(
              onTap: () => onChanged(_ranges[i].$1),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: value == _ranges[i].$1 ? const Color(0xFF7C5CFF) : Colors.transparent,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  _ranges[i].$2,
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        color: value == _ranges[i].$1 ? Colors.white : const Color(0xFF8888AA),
                        fontWeight: value == _ranges[i].$1 ? FontWeight.bold : FontWeight.normal,
                      ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _UsageHistorySection extends StatelessWidget {
  const _UsageHistorySection({required this.loading, required this.history});

  final bool loading;
  final List<dynamic> history;

  @override
  Widget build(BuildContext context) {
    if (loading && history.isEmpty) {
      return const SizedBox(height: 220, child: Center(child: CircularProgressIndicator()));
    }
    if (history.isEmpty) {
      return Container(
        height: 120,
        alignment: Alignment.center,
        decoration: _tileDecoration(),
        child: Text('暂无资源历史数据（后端需运行一段时间积累）',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: const Color(0xFF8888AA))),
      );
    }
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
      decoration: _tileDecoration(),
      child: Column(
        children: [
          const _ChartLegend(),
          const SizedBox(height: 8),
          SizedBox(height: 200, width: double.infinity, child: _UsageChart(points: _buildPoints(history))),
        ],
      ),
    );
  }

  static List<_HistoryPoint> _buildPoints(List<dynamic> raw) {
    final pts = <_HistoryPoint>[];
    for (final e in raw) {
      final m = e as Map<String, dynamic>;
      final ts = DateTime.tryParse(m['timestamp']?.toString() ?? '');
      if (ts == null) continue;
      final mem = m['memory'] as Map<String, dynamic>?;
      final memTotal = _asNum(mem?['total']);
      final memUsed = _asNum(mem?['used']);
      final gpu = m['gpu'] as Map<String, dynamic>?;
      pts.add(_HistoryPoint(
        time: ts,
        cpu: _asNum(m['cpu']),
        mem: (memTotal != null && memUsed != null && memTotal > 0)
            ? memUsed / memTotal * 100
            : null,
        gpu: _asNum(gpu?['utilization']),
        temp: _asNum(gpu?['temperature_c']),
      ));
    }
    return pts;
  }
}

class _ChartLegend extends StatelessWidget {
  const _ChartLegend();

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 16,
      runSpacing: 4,
      children: const [
        _LegendItem(color: Color(0xFF7C5CFF), label: 'CPU'),
        _LegendItem(color: Color(0xFF3DDC97), label: '内存'),
        _LegendItem(color: Color(0xFFF5B942), label: 'GPU'),
        _LegendItem(color: Color(0xFFF87171), label: 'GPU 温度°C'),
      ],
    );
  }
}

class _LegendItem extends StatelessWidget {
  const _LegendItem({required this.color, required this.label});

  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        Text(label, style: Theme.of(context).textTheme.labelSmall?.copyWith(color: const Color(0xFF8888AA))),
      ],
    );
  }
}

class _HistoryPoint {
  const _HistoryPoint({required this.time, this.cpu, this.mem, this.gpu, this.temp});

  final DateTime time;
  final double? cpu;
  final double? mem;
  final double? gpu;
  final double? temp;
}

class _UsageChart extends StatelessWidget {
  const _UsageChart({required this.points});

  final List<_HistoryPoint> points;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _UsageChartPainter(
        points: points,
        colors: const [
          Color(0xFF7C5CFF),
          Color(0xFF3DDC97),
          Color(0xFFF5B942),
          Color(0xFFF87171),
        ],
      ),
      size: Size.infinite,
    );
  }
}

class _UsageChartPainter extends CustomPainter {
  _UsageChartPainter({required this.points, required this.colors});

  final List<_HistoryPoint> points;
  final List<Color> colors;

  static const _yTicks = [0.0, 25.0, 50.0, 75.0, 100.0];

  List<List<double?>> _series() {
    return [
      [for (final p in points) p.cpu],
      [for (final p in points) p.mem],
      [for (final p in points) p.gpu],
      [for (final p in points) p.temp],
    ];
  }

  @override
  void paint(Canvas canvas, Size size) {
    const gridColor = Color(0xFF2D2D4A);
    const labelColor = Color(0xFF666688);
    const labelStyle = TextStyle(color: labelColor, fontSize: 10);

    // 绘制区域
    const left = 34.0, top = 8.0, right = 8.0, bottom = 22.0;
    final chart = Rect.fromLTRB(left, top, size.width - right, size.height - bottom);

    // 网格 + Y 轴
    final gridPaint = Paint()
      ..color = gridColor
      ..strokeWidth = 1;
    for (var i = 0; i < _yTicks.length; i++) {
      // 0 在底部、100 在顶部（与折线 y 映射一致）
      final y = chart.top + chart.height * (100 - _yTicks[i]) / 100.0;
      canvas.drawLine(Offset(chart.left, y), Offset(chart.right, y), gridPaint);
      final tp = TextPainter(
        text: TextSpan(text: '${_yTicks[i].toInt()}%', style: labelStyle),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(chart.left - 34, y - tp.height / 2));
    }

    // X 轴时间标签（首 / 尾）
    if (points.isNotEmpty) {
      final start = points.first.time;
      final end = points.last.time;
      final fmt = start.difference(end).inHours == 0
          ? (DateTime t) => '${_pad(t.hour)}:${_pad(t.minute)}'
          : (DateTime t) => '${_pad(t.month)}/${_pad(t.day)} ${_pad(t.hour)}:${_pad(t.minute)}';
      _drawTimeLabel(canvas, fmt(start), Offset(chart.left, chart.bottom + 4));
      _drawTimeLabel(canvas, fmt(end), Offset(chart.right - 40, chart.bottom + 4));
    }

    // 各系列折线
    final series = _series();
    for (var s = 0; s < series.length; s++) {
      final values = series[s];
      final color = colors[s];
      final linePaint = Paint()
        ..color = color
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round;

      final path = Path();
      final n = values.length;
      bool started = false;
      double? lastX;
      for (var i = 0; i < n; i++) {
        final v = values[i];
        final x = chart.left + chart.width * i / math.max(1, n - 1);
        if (v == null) {
          lastX = null;
          continue;
        }
        final y = chart.top + chart.height * (100 - v.clamp(0, 100)) / 100.0;
        if (!started) {
          path.moveTo(x, y);
          started = true;
        } else if (lastX != null) {
          path.lineTo(x, y);
        } else {
          path.moveTo(x, y);
        }
        lastX = x;
      }
      if (started) {
        canvas.drawPath(path, linePaint);
      }

      // 末端点
      for (var i = n - 1; i >= 0; i--) {
        if (values[i] != null) {
          final x = chart.left + chart.width * i / math.max(1, n - 1);
          final y = chart.top + chart.height * (100 - values[i]!.clamp(0, 100)) / 100.0;
          canvas.drawCircle(Offset(x, y), 3, Paint()..color = color);
          break;
        }
      }
    }
  }

  void _drawTimeLabel(Canvas canvas, String text, Offset offset) {
    final tp = TextPainter(
      text: TextSpan(text: text, style: const TextStyle(color: Color(0xFF666688), fontSize: 10)),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, offset);
  }

  String _pad(int v) => v.toString().padLeft(2, '0');

  @override
  bool shouldRepaint(covariant _UsageChartPainter old) =>
      old.points != points;
}

// ──────────────────────────────────────────────────────────────────────────
// 模型状态卡片
// ──────────────────────────────────────────────────────────────────────────
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

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A2E),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: alive ? const Color(0xFF3DDC97).withValues(alpha: 0.4) : const Color(0xFFE74C3C).withValues(alpha: 0.4),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: const Color(0xFF7C5CFF).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(Icons.smart_toy, color: Color(0xFF7C5CFF), size: 20),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(model, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: (alive ? const Color(0xFF3DDC97) : const Color(0xFFE74C3C)).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  alive ? '运行中' : '异常',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: alive ? const Color(0xFF3DDC97) : const Color(0xFFE74C3C),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text('端口 ${server['port']} · PID ${server['pid']}',
              style: theme.textTheme.bodySmall?.copyWith(color: const Color(0xFF8888AA))),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 10,
            children: [
              _Stat('tok/s', _fmtNum('tok_s'), const Color(0xFF7C5CFF)),
              _Stat('峰值', _fmtNum('tok_s_peak'), const Color(0xFF2EC4DE)),
              _Stat('日峰', _fmtNum('tok_s_peak_day'), const Color(0xFF2EC4DE)),
              _Stat('预填充', _fmtNum('prompt_tok_s'), const Color(0xFF3DDC97)),
              _Stat('入/出', '${server['total_prompt_tokens'] ?? 0}/${server['total_predicted_tokens'] ?? 0}', const Color(0xFFF5B942)),
              if (spec?['label'] != null) _Stat('投机', spec!['label'].toString(), const Color(0xFF8888AA)),
            ],
          ),
          if (mtpOn) ...[
            const SizedBox(height: 10),
            Text(
              'MTP 接受率: ${mtp?['acceptance'] != null ? '${(mtp!['acceptance'] * 100).toInt()}%' : '--'} '
              '(drafted ${mtp?['drafted'] ?? 0} / accepted ${mtp?['accepted'] ?? 0})',
              style: theme.textTheme.bodySmall?.copyWith(color: const Color(0xFFF5B942)),
            ),
          ],
          if (server['error'] != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text('${server['error']}',
                  style: theme.textTheme.bodySmall?.copyWith(color: const Color(0xFFE74C3C))),
            ),
        ],
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.label, this.value, this.color);

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: theme.textTheme.labelSmall?.copyWith(color: const Color(0xFF8888AA))),
        Text(value, style: theme.textTheme.titleSmall?.copyWith(color: color, fontWeight: FontWeight.bold)),
      ],
    );
  }
}

// ──────────────────────────────────────────────────────────────────────────
// 错误视图
// ──────────────────────────────────────────────────────────────────────────
class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.error, required this.onRetry});

  final String error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 48, color: Color(0xFFE74C3C)),
            const SizedBox(height: 12),
            Text('无法连接服务器', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(error, style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 16),
            FilledButton(onPressed: onRetry, child: const Text('重试')),
          ],
        ),
      ),
    );
  }
}

// ──────────────────────────────────────────────────────────────────────────
// 工具
// ──────────────────────────────────────────────────────────────────────────
BoxDecoration _tileDecoration() {
  return BoxDecoration(
    color: const Color(0xFF1A1A2E),
    borderRadius: BorderRadius.circular(12),
    border: Border.all(color: const Color(0xFF2D2D4A)),
  );
}

Color _usageColor(double? v) {
  if (v == null) return const Color(0xFF8888AA);
  if (v < 60) return const Color(0xFF3DDC97);
  if (v < 85) return const Color(0xFFF5B942);
  return const Color(0xFFE74C3C);
}

/// 整数值显示为整数，非整显示 1 位小数。
String _displayValue(double? value) {
  final v = value;
  if (v == null) return '--';
  return v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1);
}

double? _asNum(Object? v) {
  if (v is num) return v.toDouble();
  if (v is String) return double.tryParse(v);
  return null;
}

String _parseTime(String iso) {
  final dt = DateTime.tryParse(iso);
  if (dt == null) return iso;
  final t = dt.toLocal();
  String two(int v) => v.toString().padLeft(2, '0');
  return '${two(t.hour)}:${two(t.minute)}:${two(t.second)}';
}

String? _fmt(Object? v) {
  if (v == null) return null;
  if (v is num) {
    if (v >= 1e6) return '${(v / 1e6).toStringAsFixed(1)}M';
    if (v >= 1e3) return '${(v / 1e3).toStringAsFixed(1)}k';
    return v.toStringAsFixed(1);
  }
  return v.toString();
}

String _fmtBytes(Object? v) {
  final n = (v is num) ? v.toDouble() : double.tryParse(v?.toString() ?? '');
  if (n == null) return '--';
  if (n >= 1e12) return '${(n / 1e12).toStringAsFixed(1)}TB';
  if (n >= 1e9) return '${(n / 1e9).toStringAsFixed(1)}GB';
  if (n >= 1e6) return '${(n / 1e6).toStringAsFixed(1)}MB';
  if (n >= 1e3) return '${(n / 1e3).toStringAsFixed(1)}KB';
  return '${n.toStringAsFixed(0)}B';
}

String _fmtRate(Object? v) {
  final f = _fmt(v);
  return f == null ? '--' : '$f/s';
}
