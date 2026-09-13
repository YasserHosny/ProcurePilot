import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/core/camera/camera_capture.dart';
import 'package:procurepilot_mobile/features/delivery/quality_issue_screen.dart';
import 'package:procurepilot_mobile/features/requests/request_detail_screen.dart';

import '../../test_helpers.dart';

const valid1x1PngBytes = [
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
  0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
  0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
  0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
];

Future<void> _scrollAndTap(WidgetTester tester, Finder finder) async {
  await tester.dragUntilVisible(
    finder,
    find.byType(Scrollable).first,
    const Offset(0, -300),
  );
  // dragUntilVisible stops as soon as the element exists, which can be one
  // frame before its final on-screen position settles -- tapping right away
  // can compute a center that misses the real target. An extra settle here
  // fixes that without affecting dragUntilVisible's own ability to mount a
  // not-yet-built sliver child by scrolling to it incrementally.
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

/// Writes a real file for a test's fixture. Real `dart:io` calls made
/// directly inside a `testWidgets` body never resolve under this binding's
/// fake-async zone (the same class of issue this project's own
/// OfflineQueue/Hive testing hit) -- `tester.runAsync()` escapes to the real
/// event loop for the duration of the callback, which is exactly what plain
/// file I/O needs here.
Future<File> _writeRealFile(
  WidgetTester tester,
  String dirPrefix,
  String filename,
  List<int> bytes,
) async {
  return tester.runAsync(() async {
    final dir = await Directory.systemTemp.createTemp(dirPrefix);
    final file = File('${dir.path}/$filename');
    await file.writeAsBytes(bytes);
    return file;
  }).then((file) => file!);
}

void main() {
  group('QualityIssueScreen', () {
    late FakeRequestsApiClient fakeClient;
    late FakeCameraCapture fakeCamera;

    setUp(() {
      fakeClient = FakeRequestsApiClient();
      fakeCamera = FakeCameraCapture(available: true);
    });

    Future<void> pumpQualityIssue(
      WidgetTester tester,
      PurchaseRequest request, {
      FakeOfflineQueue? offlineQueue,
      Future<Directory> Function()? documentsDirectoryProvider,
    }) async {
      await pumpWithServices(
        tester,
        child: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  settings: RouteSettings(arguments: request),
                  builder: (_) => QualityIssueScreen(
                    documentsDirectoryProvider: documentsDirectoryProvider,
                  ),
                ),
              );
            },
            child: const Text('Open'),
          ),
        ),
        requestsApiClient: fakeClient,
        cameraCapture: fakeCamera,
        offlineQueueService: offlineQueue,
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
    }

    testWidgets(
      'zero photos MUST submit successfully when camera is unavailable (FR-007)',
      (tester) async {
        fakeCamera.available = false;
        fakeClient.reportQualityIssueResult = QualityIssue(
          id: 'issue-1',
          purchaseRequestId: 'req-1',
          reportedByMembershipId: 'member-1',
          description: 'Cracked casing on delivery',
          photos: const [],
          createdAt: DateTime.now(),
        );

        await pumpQualityIssue(tester, deliveredRequest());

        // Camera unavailable text is displayed
        expect(find.byKey(const Key('qualityIssueCameraUnavailable')), findsOneWidget);
        expect(find.byKey(const Key('qualityIssueCapturePhotoButton')), findsNothing);

        // Enter required description
        await tester.enterText(
          find.byKey(const Key('qualityIssueDescriptionField')),
          'Cracked casing on delivery',
        );

        // Submit button
        await _scrollAndTap(tester, find.byKey(const Key('qualityIssueSubmitButton')));

        // Verifies report was called and zero photos were uploaded
        expect(fakeClient.reportQualityIssueCalls, hasLength(1));
        expect(fakeClient.reportQualityIssueCalls.single['requestId'], 'req-1');
        expect(
          fakeClient.reportQualityIssueCalls.single['description'],
          'Cracked casing on delivery',
        );
        expect(fakeClient.uploadQualityIssuePhotoCalls, isEmpty);
        expect(find.text('Quality issue report submitted.'), findsOneWidget);
      },
    );

    testWidgets(
      'zero photos submits successfully when camera is available but no photo taken',
      (tester) async {
        fakeCamera.available = true;

        await pumpQualityIssue(tester, deliveredRequest());

        expect(find.byKey(const Key('qualityIssueCapturePhotoButton')), findsOneWidget);

        await tester.enterText(
          find.byKey(const Key('qualityIssueDescriptionField')),
          'Wrong item delivered',
        );

        await _scrollAndTap(tester, find.byKey(const Key('qualityIssueSubmitButton')));

        expect(fakeClient.reportQualityIssueCalls, hasLength(1));
        expect(fakeClient.uploadQualityIssuePhotoCalls, isEmpty);
        expect(find.text('Quality issue report submitted.'), findsOneWidget);
      },
    );

    testWidgets(
      'capturing a photo displays preview and remove option, submitting calls reportQualityIssue then uploadQualityIssuePhoto',
      (tester) async {
        final photoFile = await _writeRealFile(
          tester,
          'qi_test_photo',
          'test_evidence.png',
          valid1x1PngBytes,
        );

        try {
          fakeCamera.available = true;
          fakeCamera.captureResult = CapturedPhoto(filePath: photoFile.path);

          fakeClient.reportQualityIssueResult = QualityIssue(
            id: 'issue-created-99',
            purchaseRequestId: 'req-1',
            reportedByMembershipId: 'member-1',
            description: 'Severely damaged package',
            photos: const [],
            createdAt: DateTime.now(),
          );

          await pumpQualityIssue(tester, deliveredRequest());

          // Tap capture photo
          await _scrollAndTap(
            tester,
            find.byKey(const Key('qualityIssueCapturePhotoButton')),
          );

          expect(fakeCamera.captureCalls, 1);
          // Preview and remove button are visible
          expect(find.byKey(const Key('qualityIssuePhotoPreview')), findsOneWidget);
          expect(find.byKey(const Key('qualityIssueRemovePhotoButton')), findsOneWidget);
          expect(find.byKey(const Key('qualityIssueCapturePhotoButton')), findsNothing);

          // Enter description
          await tester.enterText(
            find.byKey(const Key('qualityIssueDescriptionField')),
            'Severely damaged package',
          );

          // Submit
          await _scrollAndTap(
            tester,
            find.byKey(const Key('qualityIssueSubmitButton')),
          );

          // Both issue creation and photo upload were called
          expect(fakeClient.reportQualityIssueCalls, hasLength(1));
          expect(fakeClient.uploadQualityIssuePhotoCalls, hasLength(1));
          expect(fakeClient.uploadQualityIssuePhotoCalls.single['issueId'], 'issue-created-99');
          expect(fakeClient.uploadQualityIssuePhotoCalls.single['filePath'], photoFile.path);
          expect(find.text('Quality issue report submitted.'), findsOneWidget);
        } finally {
          await tester.runAsync(() => photoFile.parent.delete(recursive: true));
        }
      },
    );

    testWidgets(
      'removing captured photo clears preview and does not upload photo on submit',
      (tester) async {
        final photoFile = await _writeRealFile(
          tester,
          'qi_remove_photo',
          'test_remove.png',
          valid1x1PngBytes,
        );

        try {
          fakeCamera.available = true;
          fakeCamera.captureResult = CapturedPhoto(filePath: photoFile.path);

          await pumpQualityIssue(tester, deliveredRequest());

          // Capture photo
          await _scrollAndTap(
            tester,
            find.byKey(const Key('qualityIssueCapturePhotoButton')),
          );
          expect(find.byKey(const Key('qualityIssuePhotoPreview')), findsOneWidget);

          // Remove photo
          await _scrollAndTap(
            tester,
            find.byKey(const Key('qualityIssueRemovePhotoButton')),
          );

          expect(find.byKey(const Key('qualityIssuePhotoPreview')), findsNothing);
          expect(find.byKey(const Key('qualityIssueCapturePhotoButton')), findsOneWidget);

          // Submit
          await tester.enterText(
            find.byKey(const Key('qualityIssueDescriptionField')),
            'Description without photo',
          );
          await _scrollAndTap(
            tester,
            find.byKey(const Key('qualityIssueSubmitButton')),
          );

          expect(fakeClient.reportQualityIssueCalls, hasLength(1));
          expect(fakeClient.uploadQualityIssuePhotoCalls, isEmpty);
        } finally {
          await tester.runAsync(() => photoFile.parent.delete(recursive: true));
        }
      },
    );

    testWidgets(
      'empty description shows validation error and does not submit',
      (tester) async {
        await pumpQualityIssue(tester, deliveredRequest());

        await _scrollAndTap(
          tester,
          find.byKey(const Key('qualityIssueSubmitButton')),
        );

        expect(find.text('Description is required.'), findsOneWidget);
        expect(fakeClient.reportQualityIssueCalls, isEmpty);
      },
    );

    testWidgets(
      'server 409 not_delivered conflict shows inline error',
      (tester) async {
        fakeClient.reportQualityIssueError = const ApiException(
          statusCode: 409,
          code: 'conflict',
          message: 'Not delivered',
          details: {'reason': 'not_delivered'},
          traceId: 'trace-409',
        );

        await pumpQualityIssue(tester, deliveredRequest());

        await tester.enterText(
          find.byKey(const Key('qualityIssueDescriptionField')),
          'Damaged goods',
        );
        await _scrollAndTap(
          tester,
          find.byKey(const Key('qualityIssueSubmitButton')),
        );

        expect(
          find.text('This request is not ready for quality issue reporting.'),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'generic API error shows generic error message',
      (tester) async {
        fakeClient.reportQualityIssueError = const ApiException(
          statusCode: 500,
          code: 'internal_error',
          message: 'Server error',
          traceId: 'trace-500',
        );

        await pumpQualityIssue(tester, deliveredRequest());

        await tester.enterText(
          find.byKey(const Key('qualityIssueDescriptionField')),
          'Damaged goods',
        );
        await _scrollAndTap(
          tester,
          find.byKey(const Key('qualityIssueSubmitButton')),
        );

        expect(
          find.text('Unable to submit quality issue report. Please try again.'),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'offline submission queues report and copies photo to stable directory',
      (tester) async {
        final offlineQueue = FakeOfflineQueue();
        final tempDir = await tester.runAsync(
          () => Directory.systemTemp.createTemp('stable_docs_test'),
        );
        final tempPhoto = File('${tempDir!.path}/transient_cam_capture.png');
        await tester.runAsync(() => tempPhoto.writeAsBytes(valid1x1PngBytes));

        try {
          fakeCamera.available = true;
          fakeCamera.captureResult = CapturedPhoto(filePath: tempPhoto.path);

          // Network is down
          fakeClient.reportQualityIssueError = Exception('No internet connection');

          await pumpQualityIssue(
            tester,
            deliveredRequest(),
            offlineQueue: offlineQueue,
            documentsDirectoryProvider: () async => tempDir,
          );

          // Capture photo
          await _scrollAndTap(
            tester,
            find.byKey(const Key('qualityIssueCapturePhotoButton')),
          );

          // Enter description
          await tester.enterText(
            find.byKey(const Key('qualityIssueDescriptionField')),
            'Offline quality issue report',
          );

          // Submit
          await _scrollAndTap(
            tester,
            find.byKey(const Key('qualityIssueSubmitButton')),
          );

          // Enqueued item
          expect(offlineQueue.pending, hasLength(1));
          final queued = offlineQueue.pending.single;
          expect(queued.endpoint, 'quality-issues');
          expect(queued.payload['request_id'], 'req-1');
          expect(queued.payload['description'], 'Offline quality issue report');
          final stablePhotoPath = queued.payload['photo_local_path'] as String?;
          expect(stablePhotoPath, isNotNull);
          expect(File(stablePhotoPath!).existsSync(), isTrue);

          expect(
            find.text('Quality issue report queued — will send when back online.'),
            findsOneWidget,
          );
        } finally {
          await tester.runAsync(() => tempDir.delete(recursive: true));
        }
      },
    );

    testWidgets(
      'offline submission queues report with zero photos when none captured',
      (tester) async {
        final offlineQueue = FakeOfflineQueue();
        fakeCamera.available = false;
        fakeClient.reportQualityIssueError = Exception('No internet connection');

        await pumpQualityIssue(
          tester,
          deliveredRequest(),
          offlineQueue: offlineQueue,
        );

        await tester.enterText(
          find.byKey(const Key('qualityIssueDescriptionField')),
          'Offline report without photo',
        );

        await _scrollAndTap(
          tester,
          find.byKey(const Key('qualityIssueSubmitButton')),
        );

        expect(offlineQueue.pending, hasLength(1));
        final queued = offlineQueue.pending.single;
        expect(queued.endpoint, 'quality-issues');
        expect(queued.payload['request_id'], 'req-1');
        expect(queued.payload['description'], 'Offline report without photo');
        expect(queued.payload.containsKey('photo_local_path'), isFalse);

        expect(
          find.text('Quality issue report queued — will send when back online.'),
          findsOneWidget,
        );
      },
    );
  });

  group('RequestDetailScreen quality issue entry point', () {
    testWidgets('delivered request shows report quality issue button', (tester) async {
      await pumpWithServices(
        tester,
        child: const RequestDetailScreen(),
        requestsApiClient: FakeRequestsApiClient(),
      );
      final context = tester.element(find.byType(RequestDetailScreen));
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          settings: RouteSettings(arguments: deliveredRequest()),
          builder: (_) => const RequestDetailScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('requestQualityIssueButton')),
        findsOneWidget,
      );
      expect(
        find.byKey(const Key('requestConfirmDeliveryButton')),
        findsNothing,
      );

      await tester.tap(find.byKey(const Key('requestQualityIssueButton')));
      await tester.pumpAndSettle();
      expect(find.byType(QualityIssueScreen), findsOneWidget);
    });

    testWidgets('ordered request does NOT show report quality issue button', (tester) async {
      await pumpWithServices(
        tester,
        child: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  settings: RouteSettings(arguments: orderedRequest()),
                  builder: (_) => const RequestDetailScreen(),
                ),
              );
            },
            child: const Text('Open'),
          ),
        ),
        requestsApiClient: FakeRequestsApiClient(),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('requestQualityIssueButton')),
        findsNothing,
      );
      expect(
        find.byKey(const Key('requestConfirmDeliveryButton')),
        findsOneWidget,
      );
    });

    testWidgets('submitted request does NOT show report quality issue button', (tester) async {
      await pumpWithServices(
        tester,
        child: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  settings: RouteSettings(arguments: submittedRequest()),
                  builder: (_) => const RequestDetailScreen(),
                ),
              );
            },
            child: const Text('Open'),
          ),
        ),
        requestsApiClient: FakeRequestsApiClient(),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('requestQualityIssueButton')),
        findsNothing,
      );
    });
  });
}

PurchaseRequest deliveredRequest() {
  return PurchaseRequest(
    id: 'req-1',
    branchId: 'branch-1',
    requestedByMembershipId: 'requester-1',
    requiredByDate: '2026-10-01',
    status: 'delivered',
    lines: const [
      PurchaseRequestLine(
        id: 'line-1',
        workspaceProductId: 'product-1',
        quantity: '5',
        quantityReceived: '5',
      ),
      PurchaseRequestLine(
        id: 'line-2',
        workspaceProductId: 'product-2',
        quantity: '2.5',
        quantityReceived: '2.5',
      ),
    ],
    hasIncompleteEstimate: false,
    createdAt: DateTime.utc(2026, 9, 13),
    deliveredAt: DateTime.utc(2026, 9, 13),
  );
}

PurchaseRequest orderedRequest() {
  return PurchaseRequest(
    id: 'req-ordered-1',
    branchId: 'branch-1',
    requestedByMembershipId: 'requester-1',
    requiredByDate: '2026-10-01',
    status: 'ordered',
    lines: const [
      PurchaseRequestLine(
        id: 'line-1',
        workspaceProductId: 'product-1',
        quantity: '5',
      ),
    ],
    hasIncompleteEstimate: false,
    createdAt: DateTime.utc(2026, 9, 13),
  );
}

PurchaseRequest submittedRequest() {
  return PurchaseRequest(
    id: 'req-sub-1',
    branchId: 'branch-1',
    requestedByMembershipId: 'requester-1',
    requiredByDate: '2026-10-01',
    status: 'submitted',
    lines: const [
      PurchaseRequestLine(
        id: 'line-1',
        workspaceProductId: 'product-1',
        quantity: '5',
      ),
    ],
    hasIncompleteEstimate: false,
    createdAt: DateTime.utc(2026, 9, 13),
  );
}
