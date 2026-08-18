import 'package:flutter/material.dart';

import 'api.dart';
import 'config.dart';

/// 连接设置：服务器地址（VPN IP）+ 端口 + read 权限 API Key。
class SetupScreen extends StatefulWidget {
  const SetupScreen({super.key});

  @override
  State<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends State<SetupScreen> {
  final _hostCtrl = TextEditingController();
  final _portCtrl = TextEditingController(text: '3003');
  final _keyCtrl = TextEditingController();

  bool _busy = false;
  String? _result; // null=未测, ok=成功, 其它=失败信息

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final host = await SecureConfig.host();
    final port = await SecureConfig.port();
    final key = await SecureConfig.apiKey();
    if (!mounted) return;
    setState(() {
      _hostCtrl.text = host;
      _portCtrl.text = '$port';
      _keyCtrl.text = key;
    });
  }

  Future<void> _save() async {
    final host = _hostCtrl.text.trim();
    final port = int.tryParse(_portCtrl.text.trim()) ?? 3003;
    final key = _keyCtrl.text.trim();
    if (host.isEmpty || key.isEmpty) {
      setState(() => _result = '服务器地址与 API Key 必填');
      return;
    }
    await SecureConfig.save(host: host, port: port, apiKey: key);
    if (!mounted) return;
    setState(() => _result = null);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('已保存配置')),
    );
  }

  Future<void> _test() async {
    final host = _hostCtrl.text.trim();
    final port = int.tryParse(_portCtrl.text.trim()) ?? 3003;
    final key = _keyCtrl.text.trim();
    if (host.isEmpty || key.isEmpty) {
      setState(() => _result = '请先填写并保存连接配置');
      return;
    }
    // 先持久化，让测试用当前配置
    await SecureConfig.save(host: host, port: port, apiKey: key);
    if (!mounted) return;
    setState(() => _busy = true);
    try {
      final api = Life2TeaApi(
        baseUrl: SecureConfig.baseUrl(host, port),
        apiKey: key,
      );
      final ok = await api.health();
      api.dispose();
      if (!mounted) return;
      setState(() => _result =
          ok ? 'ok' : '无法连接，请检查地址/端口/API Key');
    } catch (e) {
      if (!mounted) return;
      setState(() => _result = '无法连接: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('连接设置', style: theme.textTheme.headlineSmall),
          const SizedBox(height: 8),
          Text('通过 VPN 接入 Life2Tea 后端，仅提供只读监控。',
              style: theme.textTheme.bodyMedium?.copyWith(color: theme.hintColor)),
          const SizedBox(height: 24),

          TextField(
            controller: _hostCtrl,
            decoration: const InputDecoration(
              labelText: '服务器地址（VPN IP）',
              hintText: '100.81.83.59',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _portCtrl,
            decoration: const InputDecoration(
              labelText: '端口',
              border: OutlineInputBorder(),
            ),
            keyboardType: TextInputType.number,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _keyCtrl,
            obscureText: true,
            decoration: const InputDecoration(
              labelText: 'API Key（read 权限）',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 20),

          Row(
            children: [
              Expanded(
                child: FilledButton(
                  onPressed: _busy ? null : _save,
                  child: const Text('保存'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton(
                  onPressed: _busy ? null : _test,
                  child: Text(_busy ? '测试中…' : '测试连接'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),

          if (_result != null)
            Text(
              _result == 'ok' ? '连接成功 ✓' : _result!,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: _result == 'ok' ? Colors.greenAccent : Colors.amber,
              ),
            ),
        ],
      ),
    );
  }
}
