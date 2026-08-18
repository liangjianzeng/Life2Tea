import 'package:flutter_test/flutter_test.dart';

import 'package:life2tea_phone/main.dart';

void main() {
  testWidgets('App shell renders nav labels', (WidgetTester tester) async {
    await tester.pumpWidget(const Life2TeaPhoneApp());

    // Bottom nav renders both destinations.
    expect(find.text('仪表盘'), findsOneWidget);
    expect(find.text('设置'), findsOneWidget);
  });
}
