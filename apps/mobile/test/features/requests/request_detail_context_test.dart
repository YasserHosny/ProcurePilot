import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/requests/request_detail_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('RequestContextSection required-by date', () {
    setUpAll(() async {
      await initializeDateFormatting();
    });

    final request = PurchaseRequest(
      id: 'req-context-1',
      branchId: 'branch-1',
      requestedByMembershipId: 'member-1',
      requesterName: 'Sarah Connor',
      requiredByDate: '2026-10-28',
      status: 'submitted',
      lines: const [],
      hasIncompleteEstimate: false,
      createdAt: DateTime(2026, 10, 20),
    );

    testWidgets('formats required-by date in English with tabular figures', (
      tester,
    ) async {
      await pumpWithServices(
        tester,
        locale: 'en',
        child: Scaffold(
          body: SingleChildScrollView(
            child: RequestContextSection(request: request),
          ),
        ),
      );

      expect(find.text('Oct 28, 2026'), findsOneWidget);
      expect(find.textContaining('2026-10-28'), findsNothing);

      final dateWidget = tester.widget<Text>(find.text('Oct 28, 2026'));
      expect(
        dateWidget.style?.fontFeatures,
        contains(const FontFeature.tabularFigures()),
      );
    });

    testWidgets(
      'formats required-by date in Arabic with Arabic-Indic digits and tabular figures',
      (tester) async {
        await pumpWithServices(
          tester,
          locale: 'ar',
          child: Scaffold(
            body: SingleChildScrollView(
              child: RequestContextSection(request: request),
            ),
          ),
        );

        expect(find.text('٢٨ أكتوبر ٢٠٢٦'), findsOneWidget);
        expect(find.textContaining('2026-10-28'), findsNothing);

        final dateWidget = tester.widget<Text>(find.text('٢٨ أكتوبر ٢٠٢٦'));
        expect(
          dateWidget.style?.fontFeatures,
          contains(const FontFeature.tabularFigures()),
        );
        expect(RegExp(r'[0-9]').hasMatch(dateWidget.data!), isFalse);
      },
    );
  });
}
