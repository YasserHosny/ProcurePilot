import 'package:flutter/material.dart';

import '../../core/api/models.dart';
import '../../core/api/requests_api_client.dart';
import '../../core/i18n/i18n_loader.dart';
import '../requests/request_detail_screen.dart';
import '../service_provider.dart';

class ApprovalDecisionScreen extends StatefulWidget {
  const ApprovalDecisionScreen({super.key});

  @override
  State<ApprovalDecisionScreen> createState() => _ApprovalDecisionScreenState();
}

class _ApprovalDecisionScreenState extends State<ApprovalDecisionScreen> {
  final _commentController = TextEditingController();
  bool _submitting = false;
  String? _message;
  bool _messageIsError = false;

  RequestsApiClient get _apiClient =>
      ServiceProvider.of(context).requestsApiClient;
  I18nLoader get _i18n => ServiceProvider.of(context).i18n;

  @override
  void dispose() {
    _commentController.dispose();
    super.dispose();
  }

  Future<void> _submitDecision(PurchaseRequest request, String action) async {
    setState(() {
      _submitting = true;
      _message = null;
      _messageIsError = false;
    });

    try {
      if (action == 'approve') {
        await _apiClient.approveRequest(
          request.id,
          comment: _commentController.text,
        );
      } else {
        await _apiClient.rejectRequest(
          request.id,
          comment: _commentController.text,
        );
      }
      if (!mounted) return;
      setState(() {
        _message = _i18n.t(
          action == 'approve'
              ? 'approvals.approveSuccess'
              : 'approvals.rejectSuccess',
        );
        _messageIsError = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _message = _decisionErrorMessage(e);
        _messageIsError = true;
      });
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() {
        _message = _i18n.t('approvals.genericError');
        _messageIsError = true;
      });
      debugPrint('Failed to submit approval decision: $e');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  String _decisionErrorMessage(ApiException error) {
    if (error.statusCode == 409 &&
        error.details?['reason'] == 'no_pending_approval') {
      return _i18n.t('approvals.alreadyDecided');
    }
    return _i18n.t('approvals.genericError');
  }

  @override
  Widget build(BuildContext context) {
    final args = ModalRoute.of(context)?.settings.arguments;
    final i18n = _i18n;
    if (args is! PurchaseRequest) {
      return Scaffold(
        appBar: AppBar(title: Text(i18n.t('approvals.title'))),
        body: Center(child: Text(i18n.t('approvals.notAvailable'))),
      );
    }

    return Scaffold(
      appBar: AppBar(title: Text(i18n.t('approvals.title'))),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            RequestContextSection(request: args),
            const SizedBox(height: 16),
            TextField(
              key: const Key('approvalDecisionCommentField'),
              controller: _commentController,
              decoration: InputDecoration(
                labelText: i18n.t('approvals.decisionDialog.commentLabel'),
                hintText: i18n.t('approvals.decisionDialog.commentPlaceholder'),
                border: const OutlineInputBorder(),
              ),
              minLines: 2,
              maxLines: 4,
              enabled: !_submitting,
            ),
            const SizedBox(height: 16),
            if (_message != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Text(
                  _message!,
                  key: const Key('approvalDecisionMessage'),
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
                    key: const Key('approvalDecisionCancelButton'),
                    onPressed: _submitting
                        ? null
                        : () => Navigator.of(context).pop(),
                    child: Text(
                      i18n.t('approvals.decisionDialog.cancelButton'),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    key: const Key('approvalDecisionApproveButton'),
                    onPressed: _submitting
                        ? null
                        : () => _submitDecision(args, 'approve'),
                    child: Text(i18n.t('approvals.actions.approve')),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            FilledButton.tonal(
              key: const Key('approvalDecisionRejectButton'),
              onPressed: _submitting
                  ? null
                  : () => _submitDecision(args, 'reject'),
              child: Text(i18n.t('approvals.actions.reject')),
            ),
          ],
        ),
      ),
    );
  }
}
