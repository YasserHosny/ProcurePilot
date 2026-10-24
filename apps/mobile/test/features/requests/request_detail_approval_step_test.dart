import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/requests/request_detail_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('RequestApprovalStepSection', () {
    setUpAll(() async {
      await initializeDateFormatting();
    });

    const membershipId = '00000000-0000-0000-0000-000000000099';
    final localDecidedAt = DateTime(2026, 10, 24, 14, 30);

    PurchaseRequest createRequest({
      String? assignedName,
      String? assignedEmail,
      DateTime? decidedAt,
      String status = 'approved',
    }) {
      return PurchaseRequest(
        id: 'pr-test-1',
        branchId: 'branch-1',
        requestedByMembershipId: 'mem-req-1',
        requiredByDate: '2026-10-28',
        status: status,
        lines: const [],
        hasIncompleteEstimate: false,
        createdAt: DateTime(2026, 10, 20),
        approvalStep: ApprovalStep(
          id: 'step-test-1',
          assignedMembershipId: membershipId,
          assignedName: assignedName,
          assignedEmail: assignedEmail,
          source: 'branch_manager',
          status: status,
          comment: 'Approved for testing.',
          decidedAt: decidedAt,
          decidedByMembershipId: membershipId,
        ),
      );
    }

    testWidgets(
        'English: renders assigned approver email and formatted local date',
        (tester) async {
      final req = createRequest(
        assignedEmail: 'sarah@example.test',
        decidedAt: localDecidedAt,
      );

      await pumpWithServices(
        tester,
        locale: 'en',
        child: Scaffold(
          body: SingleChildScrollView(
            child: RequestApprovalStepSection(request: req),
          ),
        ),
      );

      expect(find.text('sarah@example.test'), findsOneWidget);
      expect(find.text('Oct 24, 2026 2:30\u202FPM'), findsOneWidget);
      expect(find.textContaining('2026-10-24T'), findsNothing);
      expect(find.text(membershipId), findsNothing);
      expect(find.textContaining(membershipId), findsNothing);
    });

    testWidgets(
        'Arabic: renders assigned approver email and Arabic date with Arabic-Indic digits',
        (tester) async {
      final req = createRequest(
        assignedEmail: 'sarah@example.test',
        decidedAt: localDecidedAt,
      );

      await pumpWithServices(
        tester,
        locale: 'ar',
        child: Scaffold(
          body: SingleChildScrollView(
            child: RequestApprovalStepSection(request: req),
          ),
        ),
      );

      expect(find.text('sarah@example.test'), findsOneWidget);
      expect(find.text('٢٤ أكتوبر ٢٠٢٦ ٢:٣٠ م'), findsOneWidget);
      expect(find.textContaining('٢٠٢٦'), findsOneWidget);

      final dateRowText = tester.widget<Text>(
        find.text('٢٤ أكتوبر ٢٠٢٦ ٢:٣٠ م'),
      );
      expect(RegExp(r'[0-9]').hasMatch(dateRowText.data!), isFalse);

      expect(find.textContaining('2026-10-24T'), findsNothing);
      expect(find.text(membershipId), findsNothing);
      expect(find.textContaining(membershipId), findsNothing);
    });

    testWidgets(
        'Fallback in English: renders Unknown approver when name and email are null',
        (tester) async {
      final req = createRequest(
        assignedName: null,
        assignedEmail: null,
        decidedAt: localDecidedAt,
      );

      await pumpWithServices(
        tester,
        locale: 'en',
        child: Scaffold(
          body: SingleChildScrollView(
            child: RequestApprovalStepSection(request: req),
          ),
        ),
      );

      expect(find.text('Unknown approver'), findsOneWidget);
      expect(find.text(membershipId), findsNothing);
      expect(find.textContaining(membershipId), findsNothing);
    });

    testWidgets(
        'Fallback in Arabic: renders معتمد غير معروف when name and email are null',
        (tester) async {
      final req = createRequest(
        assignedName: null,
        assignedEmail: null,
        decidedAt: localDecidedAt,
      );

      await pumpWithServices(
        tester,
        locale: 'ar',
        child: Scaffold(
          body: SingleChildScrollView(
            child: RequestApprovalStepSection(request: req),
          ),
        ),
      );

      expect(find.text('معتمد غير معروف'), findsOneWidget);
      expect(find.text(membershipId), findsNothing);
      expect(find.textContaining(membershipId), findsNothing);
    });
  });
}
