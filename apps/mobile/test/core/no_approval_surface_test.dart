import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/main.dart' as app;

/// FR-009 proof at the code-path level.
///
/// This test does not render any widget. It inspects the mobile API clients
/// and the registered route table to prove that no mobile-reachable code path
/// calls or names `POST /requests/{id}/approve` or `/reject`. This is
/// deliberately stronger than a widget-only test: it catches an approve/reject
/// call even if it is never wired to a visible button.
void main() {
  const apiFiles = [
    'lib/core/api/mobile_api_client.dart',
    'lib/core/api/approvals_api_client.dart',
  ];

  // Require a path-segment boundary so that `/approvals/pending` does not
  // falsely match `/approve`.
  final endpointPattern = RegExp(
    r'/approve(?![a-zA-Z0-9_])|/reject(?![a-zA-Z0-9_])',
    caseSensitive: false,
  );

  group('No approval/rejection API surface', () {
    for (final path in apiFiles) {
      test('$path contains no /approve or /reject endpoint paths', () {
        final file = File(path);
        final content = file.readAsStringSync();
        expect(
          endpointPattern.hasMatch(content),
          isFalse,
          reason: 'Found an approve/reject endpoint path reference in $path',
        );
      });
    }
  });

  group('No approval/rejection route surface', () {
    test('app route table contains no approve/reject route names', () {
      final routeNamePattern = RegExp(r'approve|reject', caseSensitive: false);
      for (final name in app.appRoutes.keys) {
        expect(
          routeNamePattern.hasMatch(name),
          isFalse,
          reason: 'Route name "$name" matches approve/reject',
        );
      }
    });
  });
}
