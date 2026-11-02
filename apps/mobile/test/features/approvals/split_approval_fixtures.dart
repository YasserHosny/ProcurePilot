import 'package:procurepilot_mobile/core/api/models.dart';

const splitGroupId = 'group-1';

List<PurchaseRequest> splitApprovalRequests() => [
  for (var index = 0; index < 2; index++)
    PurchaseRequest.fromJson({
      'id': 'split-req-${index + 1}',
      'branch_id': 'branch-1',
      'requested_by_membership_id': 'requester-1',
      'requester_name': 'Sarah Connor',
      'required_by_date': '2026-10-30',
      'status': 'submitted',
      'lines': [
        {
          'id': 'split-line-$index',
          'workspace_product_id': 'product-$index',
          'product_name': index == 0 ? 'Rice' : 'Oil',
          'quantity': '1',
        },
      ],
      'estimated_total': {
        'amount': index == 0 ? '2773.00' : '1290.00',
        'currency': 'SAR',
      },
      'has_incomplete_estimate': false,
      'budget_status': {
        'remaining_amount': {'amount': '2000.00', 'currency': 'SAR'},
        'exceeds': index == 0,
      },
      'created_at': '2026-10-29T12:00:00Z',
      'request_group': {
        'id': splitGroupId,
        'rfq_id': 'rfq-1234-5678',
        'position': index + 1,
        'size': 2,
        'combined_total': {'amount': '4063.00', 'currency': 'SAR'},
        'best_single_total': {'amount': '4137.00', 'currency': 'SAR'},
        'saving': {'amount': '74.00', 'currency': 'SAR'},
        'sibling_request_ids': ['split-req-${index == 0 ? 2 : 1}'],
      },
      'source': {
        'rfq_id': 'rfq-1234-5678',
        'rfq_response_id': 'response-$index',
        'quotation_id': 'quotation-$index',
        'supplier_id': 'supplier-$index',
        'supplier_name': index == 0 ? 'الذهبي' : 'الوفرة',
      },
    }),
];
