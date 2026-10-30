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

    for (final locale in ['en', 'ar']) {
      testWidgets('no budget renders without remaining amount ($locale)', (
        tester,
      ) async {
        final json = request.toJson();
        json['budget_status'] = {
          'remaining_amount': null,
          'exceeds': false,
          'status': 'no_budget',
          'reason_code': 'no_budget_at_cost_centre_level',
        };
        final noBudgetRequest = PurchaseRequest.fromJson(json);
        await pumpWithServices(
          tester,
          locale: locale,
          child: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                  settings: RouteSettings(arguments: noBudgetRequest),
                  builder: (_) => const RequestDetailScreen(),
                ),
              ),
              child: const Text('Open'),
            ),
          ),
        );
        await tester.tap(find.text('Open'));
        await tester.pumpAndSettle();

        expect(
          find.text(
            locale == 'en' ? 'No budget configured' : 'لا توجد ميزانية محددة',
          ),
          findsOneWidget,
        );
        expect(
          find.text(
            locale == 'en'
                ? 'No budget at cost-centre level'
                : 'لا توجد ميزانية على مستوى مركز التكلفة',
          ),
          findsOneWidget,
        );
        expect(
          find.textContaining(
            locale == 'en' ? 'Remaining budget' : 'الميزانية المتبقية',
          ),
          findsNothing,
        );
        expect(find.byKey(const Key('requestBudgetExceeded')), findsNothing);
        expect(tester.takeException(), isNull);
      });
    }

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
