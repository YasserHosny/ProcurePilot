import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/low_stock/low_stock_report_screen.dart';

import '../../test_helpers.dart';

void main() {
  testWidgets(
    'AppBar title does not overflow on a 360x640 surface with back button in Arabic',
    (tester) async {
      tester.view.physicalSize = const Size(360, 640);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      final fakeRequestsClient = FakeRequestsApiClient()
        ..branches = [
          Branch(
            id: 'b-1',
            name: 'الفرع الرئيسي',
            isActive: true,
            createdAt: DateTime(2026, 1, 1),
          ),
        ];

      await pumpWithServices(
        tester,
        child: Builder(
          builder: (context) => ElevatedButton(
            key: const Key('pushLowStockButton'),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const LowStockReportScreen(),
                ),
              );
            },
            child: const Text('Open'),
          ),
        ),
        requestsApiClient: fakeRequestsClient,
        locale: 'ar',
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('pushLowStockButton')));
      await tester.pumpAndSettle();

      expect(find.byType(LowStockReportScreen), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
