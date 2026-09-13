import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

import '../../core/api/models.dart';
import '../../core/api/requests_api_client.dart';
import '../../core/camera/camera_capture.dart';
import '../../core/i18n/i18n_loader.dart';
import '../requests/request_detail_screen.dart';
import '../service_provider.dart';

/// Screen for reporting a delivery quality issue (e.g. damage, defect, wrong item)
/// against a delivered purchase request (User Story 3).
///
/// Photo evidence is optional per FR-007; zero photos must submit successfully.
class QualityIssueScreen extends StatefulWidget {
  const QualityIssueScreen({
    super.key,
    this.documentsDirectoryProvider,
  });

  /// Injected directory provider for stable photo caching when offline.
  /// Defaults to [getApplicationDocumentsDirectory].
  final Future<Directory> Function()? documentsDirectoryProvider;

  @override
  State<QualityIssueScreen> createState() => _QualityIssueScreenState();
}

class _QualityIssueScreenState extends State<QualityIssueScreen> {
  final _descriptionController = TextEditingController();
  PurchaseRequest? _request;
  CapturedPhoto? _capturedPhoto;
  bool _cameraAvailable = false;
  bool _cameraChecked = false;
  bool _submitting = false;
  String? _idempotencyKey;
  String? _descriptionError;
  String? _message;
  bool _messageIsError = false;

  RequestsApiClient get _apiClient =>
      ServiceProvider.of(context).requestsApiClient;
  CameraCapture get _cameraCapture =>
      ServiceProvider.of(context).cameraCapture;
  I18nLoader get _i18n => ServiceProvider.of(context).i18n;

  @override
  void dispose() {
    _descriptionController.dispose();
    super.dispose();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_cameraChecked) {
      _cameraChecked = true;
      _checkCameraAvailability();
    }
  }

  Future<void> _checkCameraAvailability() async {
    try {
      final available = await _cameraCapture.isAvailable();
      if (mounted) setState(() => _cameraAvailable = available);
    } on Exception catch (e) {
      debugPrint('Failed to check camera availability: $e');
    }
  }

  Future<void> _capturePhoto() async {
    try {
      final photo = await _cameraCapture.capturePhoto();
      if (!mounted) return;
      if (photo != null) {
        setState(() => _capturedPhoto = photo);
      }
    } on Exception catch (e) {
      debugPrint('Failed to capture photo: $e');
    }
  }

  Future<void> _submit(PurchaseRequest request) async {
    final description = _descriptionController.text.trim();
    if (description.isEmpty) {
      setState(() => _descriptionError = _i18n.t('qualityIssue.descriptionRequired'));
      return;
    }

    setState(() {
      _descriptionError = null;
      _submitting = true;
      _message = null;
      _messageIsError = false;
    });

    _idempotencyKey ??= const Uuid().v4();
    final key = _idempotencyKey!;

    try {
      final issue = await _apiClient.reportQualityIssue(request.id, description);
      if (_capturedPhoto != null) {
        await _apiClient.uploadQualityIssuePhoto(
          issue.id,
          _capturedPhoto!.filePath,
        );
      }
      if (!mounted) return;
      setState(() {
        _message = _i18n.t('qualityIssue.successMessage');
        _messageIsError = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _message = _qualityIssueErrorMessage(e);
        _messageIsError = true;
      });
    } on Exception catch (e) {
      final queued = await _queueQualityIssue(
        requestId: request.id,
        description: description,
        photo: _capturedPhoto,
        idempotencyKey: key,
      );
      if (!mounted) return;
      if (queued) {
        setState(() {
          _message = _i18n.t('qualityIssue.queuedMessage');
          _messageIsError = false;
        });
        return;
      }
      setState(() {
        _message = _i18n.t('qualityIssue.genericError');
        _messageIsError = true;
      });
      debugPrint('Failed to submit quality issue: $e');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<bool> _queueQualityIssue({
    required String requestId,
    required String description,
    required CapturedPhoto? photo,
    required String idempotencyKey,
  }) async {
    final queue = ServiceProvider.of(context).offlineQueueService;
    if (queue == null) return false;

    String? stableLocalPath;
    if (photo != null) {
      stableLocalPath = await _copyPhotoToStablePath(
        photo.filePath,
        idempotencyKey,
      );
    }

    await queue.createAndEnqueue(
      endpoint: 'quality-issues',
      payload: {
        'request_id': requestId,
        'description': description,
        if (stableLocalPath != null) 'photo_local_path': stableLocalPath,
      },
      idempotencyKey: idempotencyKey,
    );
    return true;
  }

  Future<String> _copyPhotoToStablePath(
    String sourcePath,
    String idempotencyKey,
  ) async {
    final Directory dir;
    if (widget.documentsDirectoryProvider != null) {
      dir = await widget.documentsDirectoryProvider!();
    } else {
      dir = await getApplicationDocumentsDirectory();
    }
    // Synchronous dart:io calls from here on: this runs from a button's
    // onPressed handler, and the async variants of these same calls never
    // resolve under a widget test's fake-async zone (the same class of
    // issue this project's OfflineQueue/Hive testing already hit) --
    // sync calls complete on the calling isolate immediately rather than
    // depending on the event loop's async I/O completion machinery, which
    // sidesteps that incompatibility. A tiny evidence photo makes the
    // blocking cost negligible.
    dir.createSync(recursive: true);

    final ext = sourcePath.contains('.') ? sourcePath.split('.').last : 'jpg';
    final targetPath = '${dir.path}/quality_issue_${idempotencyKey}_photo.$ext';
    final sourceFile = File(sourcePath);
    if (sourceFile.existsSync()) {
      final copied = sourceFile.copySync(targetPath);
      return copied.path;
    } else {
      final target = File(targetPath);
      target.createSync(recursive: true);
      return target.path;
    }
  }

  String _qualityIssueErrorMessage(ApiException error) {
    if (error.statusCode == 409 && error.details?['reason'] == 'not_delivered') {
      return _i18n.t('qualityIssue.notDeliveredError');
    }
    return _i18n.t('qualityIssue.genericError');
  }

  @override
  Widget build(BuildContext context) {
    final args = ModalRoute.of(context)?.settings.arguments;
    final i18n = _i18n;
    final initialRequest = _request ?? (args is PurchaseRequest ? args : null);

    if (initialRequest == null) {
      return Scaffold(
        appBar: AppBar(title: Text(i18n.t('qualityIssue.title'))),
        body: Center(child: Text(i18n.t('qualityIssue.notAvailable'))),
      );
    }

    _request = initialRequest;

    return Scaffold(
      appBar: AppBar(title: Text(i18n.t('qualityIssue.title'))),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            RequestContextSection(request: initialRequest),
            const SizedBox(height: 16),
            TextField(
              key: const Key('qualityIssueDescriptionField'),
              controller: _descriptionController,
              enabled: !_submitting,
              maxLines: 4,
              onChanged: (_) {
                if (_descriptionError != null) {
                  setState(() => _descriptionError = null);
                }
              },
              decoration: InputDecoration(
                labelText: i18n.t('qualityIssue.descriptionLabel'),
                hintText: i18n.t('qualityIssue.descriptionPlaceholder'),
                errorText: _descriptionError,
                border: const OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              i18n.t('qualityIssue.photoEvidenceTitle'),
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            _buildCameraSection(context),
            const SizedBox(height: 16),
            if (_message != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Text(
                  _message!,
                  key: const Key('qualityIssueMessage'),
                  style: TextStyle(
                    color: _messageIsError
                        ? Theme.of(context).colorScheme.error
                        : Theme.of(context).colorScheme.primary,
                  ),
                ),
              ),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    key: const Key('qualityIssueCancelButton'),
                    onPressed: _submitting
                        ? null
                        : () => Navigator.of(context).pop(),
                    child: Text(i18n.t('qualityIssue.cancelButton')),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    key: const Key('qualityIssueSubmitButton'),
                    onPressed: _submitting
                        ? null
                        : () => _submit(initialRequest),
                    child: Text(
                      _submitting
                          ? i18n.t('qualityIssue.submittingButton')
                          : i18n.t('qualityIssue.submitButton'),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCameraSection(BuildContext context) {
    if (!_cameraAvailable) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Text(
          _i18n.t('qualityIssue.cameraUnavailable'),
          key: const Key('qualityIssueCameraUnavailable'),
          style: TextStyle(color: Theme.of(context).disabledColor),
        ),
      );
    }

    if (_capturedPhoto != null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: Container(
              height: 200,
              width: double.infinity,
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              child: Image.file(
                File(_capturedPhoto!.filePath),
                key: const Key('qualityIssuePhotoPreview'),
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) => Center(
                  child: Icon(
                    Icons.broken_image,
                    size: 48,
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            key: const Key('qualityIssueRemovePhotoButton'),
            onPressed: _submitting
                ? null
                : () => setState(() => _capturedPhoto = null),
            icon: const Icon(Icons.delete_outline),
            label: Text(_i18n.t('qualityIssue.removePhotoButton')),
          ),
        ],
      );
    }

    return OutlinedButton.icon(
      key: const Key('qualityIssueCapturePhotoButton'),
      onPressed: _submitting ? null : _capturePhoto,
      icon: const Icon(Icons.camera_alt),
      label: Text(_i18n.t('qualityIssue.capturePhotoButton')),
    );
  }
}
