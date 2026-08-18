import 'package:flutter/material.dart';

import 'dashboard_screen.dart';
import 'setup_screen.dart';

void main() {
  runApp(const Life2TeaPhoneApp());
}

class Life2TeaPhoneApp extends StatelessWidget {
  const Life2TeaPhoneApp({super.key});

  static const _bg = Color(0xFF0F0F1A);
  static const _surface = Color(0xFF1A1A2E);
  static const _accent = Color(0xFF7C5CFF);
  static const _text = Color(0xFFE0E0FF);
  static const _muted = Color(0xFF8888AA);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Life2Tea 监控',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: _bg,
        colorScheme: const ColorScheme.dark(
          surface: _surface,
          primary: _accent,
          onPrimary: _text,
          onSurface: _text,
          error: Color(0xFFE74C3C),
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: _surface,
          foregroundColor: _text,
        ),
        cardColor: _surface,
        hintColor: _muted,
        navigationBarTheme: const NavigationBarThemeData(
          backgroundColor: _surface,
          indicatorColor: _accent,
        ),
        dividerTheme: const DividerThemeData(color: Color(0xFF2D2D4A)),
      ),
      home: const HomeShell(),
    );
  }
}

/// 底部导航壳：仪表盘 / 设置。
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _pages = [DashboardScreen(), SetupScreen()];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.speed),
            label: '仪表盘',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings),
            label: '设置',
          ),
        ],
      ),
    );
  }
}
