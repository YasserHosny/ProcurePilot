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
  });
}
