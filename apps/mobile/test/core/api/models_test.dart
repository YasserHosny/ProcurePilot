import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';

import '../../test_helpers.dart';

void main() {
  group('models parse and display helpers', () {
    late dynamic i18nEn;
    late dynamic i18nAr;

    setUpAll(() async {
      i18nEn = await loadTestI18n(locale: 'en');
      i18nAr = await loadTestI18n(locale: 'ar');
    });

    group('PurchaseRequest', () {
      test('parses requester_name and requester_email from json', () {
        final json = {
          'id': 'req-1',
          'branch_id': 'branch-1',
          'requested_by_membership_id': '00000000-0000-0000-0000-000000000001',
          'requester_name': 'Sarah Connor',
          'requester_email': 'sarah@example.com',
          'required_by_date': '2026-10-01',
          'status': 'submitted',
          'lines': <Map<String, dynamic>>[],
          'has_incomplete_estimate': false,
          'created_at': '2026-09-13T10:00:00Z',
        };

        final req = PurchaseRequest.fromJson(json);
        expect(req.requesterName, 'Sarah Connor');
        expect(req.requesterEmail, 'sarah@example.com');
        expect(req.requesterDisplayName(i18nEn), 'Sarah Connor');
      });

      test('parses auto_prepared guardrail provenance and round-trips it', () {
        final json = {
          'id': 'req-1',
          'branch_id': 'branch-1',
          'requested_by_membership_id': '00000000-0000-0000-0000-000000000001',
          'required_by_date': '2026-10-01',
          'status': 'draft',
          'lines': <Map<String, dynamic>>[],
          'has_incomplete_estimate': false,
          'created_at': '2026-09-13T10:00:00Z',
          'auto_prepared': {
            'guardrail_id': 'g-1',
            'rfq_id': 'rfq-1',
            'supplier_id': 's-1',
            'supplier_name': 'Nile Bakery',
            'created_at': '2026-10-18T09:00:00Z',
          },
        };

        final req = PurchaseRequest.fromJson(json);
        expect(req.autoPrepared?.guardrailId, 'g-1');
        expect(req.autoPrepared?.supplierName, 'Nile Bakery');
        expect(req.autoPrepared?.createdAt, DateTime.utc(2026, 10, 18, 9));
        expect(
          PurchaseRequest.fromJson(req.toJson()).autoPrepared?.supplierId,
          's-1',
        );

        json.remove('auto_prepared');
        expect(PurchaseRequest.fromJson(json).autoPrepared, isNull);
      });

      test('falls back to email when name is null or whitespace', () {
        final req = PurchaseRequest(
          id: 'req-1',
          branchId: 'branch-1',
          requestedByMembershipId: '00000000-0000-0000-0000-000000000001',
          requesterName: '   ',
          requesterEmail: 'sarah@example.com',
          requiredByDate: '2026-10-01',
          status: 'submitted',
          lines: const [],
          hasIncompleteEstimate: false,
          createdAt: DateTime.utc(2026, 9, 13),
        );
        expect(req.requesterDisplayName(i18nEn), 'sarah@example.com');
      });

      test('falls back to localised unknown requester when name and email are missing', () {
        final req = PurchaseRequest(
          id: 'req-1',
          branchId: 'branch-1',
          requestedByMembershipId: '00000000-0000-0000-0000-000000000001',
          requesterName: null,
          requesterEmail: null,
          requiredByDate: '2026-10-01',
          status: 'submitted',
          lines: const [],
          hasIncompleteEstimate: false,
          createdAt: DateTime.utc(2026, 9, 13),
        );
        expect(req.requesterDisplayName(i18nEn), 'Unknown requester');
        expect(req.requesterDisplayName(i18nAr), 'مقدم طلب غير معروف');
        expect(req.requesterDisplayName(i18nEn), isNot(contains('00000000-0000')));
      });
    });

    group('PurchaseRequestLine', () {
      test('parses product_name, base_unit, and pack_base_quantity from json', () {
        final json = {
          'id': 'line-1',
          'workspace_product_id': '00000000-0000-0000-0000-000000000002',
          'quantity': '2.000000',
          'product_name': 'Vegetable Oil 18L',
          'base_unit': 'litre',
          'pack_base_quantity': '18.000000',
        };

        final line = PurchaseRequestLine.fromJson(json);
        expect(line.productName, 'Vegetable Oil 18L');
        expect(line.baseUnit, 'litre');
        expect(line.packBaseQuantity, '18.000000');
        expect(line.productDisplayName(i18nEn), 'Vegetable Oil 18L');
      });

      test('falls back to localised unknown product when name is null or whitespace', () {
        final line = const PurchaseRequestLine(
          id: 'line-1',
          workspaceProductId: '00000000-0000-0000-0000-000000000002',
          quantity: '2.000000',
          productName: '  ',
        );
        expect(line.productDisplayName(i18nEn), 'Unknown product');
        expect(line.productDisplayName(i18nAr), 'منتج غير معروف');
        expect(line.productDisplayName(i18nEn), isNot(contains('00000000-0000')));
      });
    });

    group('ApprovalStep', () {
      test('parses assigned_name and assigned_email from json and round-trips to json', () {
        final json = {
          'id': 'step-1',
          'assigned_membership_id': '00000000-0000-0000-0000-000000000001',
          'assigned_name': 'Sarah Connor',
          'assigned_email': 'sarah@example.com',
          'source': 'branch_manager',
          'status': 'pending',
        };

        final step = ApprovalStep.fromJson(json);
        expect(step.assignedName, 'Sarah Connor');
        expect(step.assignedEmail, 'sarah@example.com');
        expect(step.assignedDisplayName(i18nEn), 'Sarah Connor');
        expect(step.assignedDisplayName(i18nAr), 'Sarah Connor');
        expect(step.toJson()['assigned_name'], 'Sarah Connor');
        expect(step.toJson()['assigned_email'], 'sarah@example.com');
      });

      test('falls back to email when name is null or whitespace', () {
        final step = ApprovalStep(
          id: 'step-1',
          assignedMembershipId: '00000000-0000-0000-0000-000000000001',
          assignedName: '   ',
          assignedEmail: 'sarah@example.com',
          source: 'branch_manager',
          status: 'pending',
        );
        expect(step.assignedDisplayName(i18nEn), 'sarah@example.com');
      });

      test('falls back to localised unknown approver when name and email are missing', () {
        final step = ApprovalStep(
          id: 'step-1',
          assignedMembershipId: '00000000-0000-0000-0000-000000000001',
          assignedName: null,
          assignedEmail: null,
          source: 'branch_manager',
          status: 'pending',
        );
        expect(step.assignedDisplayName(i18nEn), 'Unknown approver');
        expect(step.assignedDisplayName(i18nAr), 'معتمد غير معروف');
        expect(step.assignedDisplayName(i18nEn), isNot(contains('00000000-0000')));
        expect(step.toJson().containsKey('assigned_name'), isFalse);
        expect(step.toJson().containsKey('assigned_email'), isFalse);
      });
    });
  });
}
