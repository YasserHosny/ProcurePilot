import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/main.dart' as app;

/// R2.3 approval-surface proof at the code-path level.
///
/// This test does not render any widget. It inspects the mobile API clients
/// and the registered route table to prove that the now-authorized mobile
/// decision surface still calls only the shared request decision endpoints.
void main() {
  // Scans every .dart file actually present under lib/core/api/ rather than a hardcoded
  // filename list — a hardcoded list stays green when a NEW client file is added with an
  // approve/reject call, which defeats the whole point of this test (PR review finding, PR #19).
  // This also means the test is unaffected by future client files being added or renamed.
  final apiDir = Directory('lib/core/api');
  final apiFiles = apiDir
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => f.path.endsWith('.dart'))
      .map((f) => f.path)
      .toList();

  // Require a path-segment boundary so that `/approvals/pending` does not
  // falsely match `/approve`.
  final endpointPattern = RegExp(
    r'/approve(?![a-zA-Z0-9_])|/reject(?![a-zA-Z0-9_])',
    caseSensitive: false,
  );

  test('lib/core/api/ actually has client files to scan', () {
    // Guards against the discovery mechanism itself silently finding nothing (e.g. a wrong
    // working directory) and this whole test group passing vacuously.
    expect(apiFiles, isNotEmpty);
    expect(apiFiles.any((p) => p.endsWith('mobile_api_client.dart')), isTrue);
  });

  group('No divergent approval/rejection API surface', () {
    for (final path in apiFiles) {
      test(
        '$path keeps approve/reject endpoint paths in RequestsApiClient only',
        () {
          final file = File(path);
          final content = file.readAsStringSync();
          if (path.endsWith('requests_api_client.dart')) {
            expect(content, contains("action: 'approve'"));
            expect(content, contains("action: 'reject'"));
          } else {
            expect(
              endpointPattern.hasMatch(content),
              isFalse,
              reason:
                  'Found an approve/reject endpoint path reference in $path',
            );
          }
        },
      );
    }
  });

  group('No direct approve/reject route surface', () {
    test('app route table contains no direct approve/reject route names', () {
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
