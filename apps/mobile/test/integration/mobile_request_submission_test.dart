import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:procurepilot_mobile/core/api/approvals_api_client.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/core/api/requests_api_client.dart';

/// End-to-end proof that a request created via the mobile Dart client is
/// correctly routed through the same `/requests` pipeline the web app uses.
///
/// The test creates a request, submits it, then asserts the submitted request
/// appears in `GET /approvals/pending` for the resolved approver. This proves
/// SC-003's "no channel-specific behaviour gap" directly, not by inspection.
///
/// Running this test requires a live `apps/api` instance backed by a real
/// Postgres with the full migration set applied, plus a valid Supabase JWT
/// for a workspace member who can raise requests and an approver who can
/// receive them. Configure via environment variables (see [_config] below).
/// If the required environment is unavailable, the test is skipped.
void main() {
  final config = _config();

  group('Mobile request submission end-to-end', () {
    test(
      'request created via mobile client appears in approvals pending queue',
      () async {
        final requestsClient = RequestsApiClient(
          apiBaseUrl: config.apiBaseUrl,
          httpClient: http.Client(),
        )..accessToken = config.requesterAccessToken;

        final approvalsClient = ApprovalsApiClient(
          apiBaseUrl: config.apiBaseUrl,
          httpClient: http.Client(),
        )..accessToken = config.approverAccessToken;

        // 1. Discover a branch and product to use in the request.
        final branches = await requestsClient.listBranches();
        expect(branches.items, isNotEmpty, reason: 'Workspace needs a branch');
        final branch = branches.items.first;

        final products = await requestsClient.searchCatalogue(
          query: config.productSearchKeyword,
        );
        expect(
          products.items,
          isNotEmpty,
          reason: 'Workspace needs at least one catalogue product',
        );
        final product = products.items.first;

        // 2. Create and submit a request through the mobile client.
        final requiredBy = _futureDate(days: 7);
        final create = PurchaseRequestCreate(
          branchId: branch.id,
          requiredByDate: requiredBy,
          lines: [
            PurchaseRequestLineInput(
              workspaceProductId: product.id,
              quantity: '10',
              note: 'E2E mobile submission',
            ),
          ],
        );

        final draft = await requestsClient.createRequest(
          create,
          idempotencyKey: _uuid(),
        );
        expect(draft.status, 'draft');
        expect(draft.lines.length, 1);

        final submitted = await requestsClient.submitRequest(
          draft.id,
          idempotencyKey: _uuid(),
        );
        expect(submitted.status, 'submitted');
        expect(submitted.approvalStep, isNotNull);

        // 3. Verify the same request is visible in the approval queue.
        final pending = await approvalsClient.listPendingApprovals();
        final matched = pending.items.any(
          (item) => item['id'] == submitted.id,
        );
        expect(
          matched,
          isTrue,
          reason:
              'Request ${submitted.id} should appear in GET /approvals/pending',
        );
      },
      skip: config.skipReason,
    );
  });
}

class _TestConfig {
  const _TestConfig({
    required this.apiBaseUrl,
    required this.requesterAccessToken,
    required this.approverAccessToken,
    required this.productSearchKeyword,
    this.skipReason,
  });

  final String apiBaseUrl;
  final String requesterAccessToken;
  final String approverAccessToken;
  final String productSearchKeyword;
  final String? skipReason;
}

_TestConfig _config() {
  const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );
  const requesterToken = String.fromEnvironment(
    'E2E_REQUESTER_TOKEN',
    defaultValue: '',
  );
  const approverToken = String.fromEnvironment(
    'E2E_APPROVER_TOKEN',
    defaultValue: '',
  );
  const productKeyword = String.fromEnvironment(
    'E2E_PRODUCT_KEYWORD',
    defaultValue: 'milk',
  );

  if (apiBaseUrl.isEmpty ||
      requesterToken.isEmpty ||
      approverToken.isEmpty) {
    return const _TestConfig(
      apiBaseUrl: '',
      requesterAccessToken: '',
      approverAccessToken: '',
      productSearchKeyword: '',
      skipReason:
          'E2E_REQUESTER_TOKEN and E2E_APPROVER_TOKEN must be set to run the real HTTP integration test',
    );
  }

  return _TestConfig(
    apiBaseUrl: apiBaseUrl,
    requesterAccessToken: requesterToken,
    approverAccessToken: approverToken,
    productSearchKeyword: productKeyword,
  );
}

String _futureDate({required int days}) {
  final date = DateTime.now().toUtc().add(Duration(days: days));
  return '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-'
      '${date.day.toString().padLeft(2, '0')}';
}

String _uuid() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  // Version 4 UUID
  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;
  final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-'
      '${hex.substring(8, 12)}-'
      '${hex.substring(12, 16)}-'
      '${hex.substring(16, 20)}-'
      '${hex.substring(20, 32)}';
}

