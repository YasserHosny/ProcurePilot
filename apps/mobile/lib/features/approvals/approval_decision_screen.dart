import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../core/api/models.dart';
import '../../core/api/requests_api_client.dart';
import '../../core/format/money_format.dart';
import '../../core/i18n/i18n_loader.dart';
import '../../core/theme/ledger_typography.dart';
import '../requests/request_detail_screen.dart';
import '../service_provider.dart';
import 'approval_group.dart';

class ApprovalDecisionScreen extends StatefulWidget {
  const ApprovalDecisionScreen({super.key});

  @override
  State<ApprovalDecisionScreen> createState() => _ApprovalDecisionScreenState();
}

class _ApprovalDecisionScreenState extends State<ApprovalDecisionScreen> {
  final _commentController = TextEditingController();
  bool _submitting = false;
  bool _succeeded = false;
  String? _message;
  bool _messageIsError = false;
  bool _initialised = false;
  ApprovalGroup? _group;
  bool _groupLoading = false;
  bool _groupLoadFailed = false;

  RequestsApiClient get _apiClient =>
      ServiceProvider.of(context).requestsApiClient;
  I18nLoader get _i18n => ServiceProvider.of(context).i18n;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_initialised) return;
    _initialised = true;
    final args = ModalRoute.of(context)?.settings.arguments;
    if (args is ApprovalGroup) {
      _group = args;
    } else if (args is PurchaseRequest && args.requestGroup != null) {
      _group = ApprovalGroup(summary: args.requestGroup!, requests: [args]);
    }
    final group = _group;
    if (group != null && group.requests.length < group.summary.size) {
      _groupLoading = true;
      _loadGroupMembers(group);
    }
  }

  /// A group may cross the pending list's page boundary. Load missing siblings
  /// before enabling a decision so the approver can review the entire split.
  Future<void> _loadGroupMembers(ApprovalGroup group) async {
    try {
      final knownIds = group.requests.map((r) => r.id).toSet();
      final missingIds = group.requests
          .expand((r) => r.requestGroup!.siblingRequestIds)
          .toSet()
          .difference(knownIds);
      final missing = await Future.wait(missingIds.map(_apiClient.getRequest));
      final requests = [...group.requests, ...missing];
      if (requests.length != group.summary.size ||
          requests.any((r) => r.requestGroup?.id != group.summary.id)) {
        throw const FormatException();
      }
      if (!mounted) return;
      setState(
        () =>
            _group = ApprovalGroup(summary: group.summary, requests: requests),
      );
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() {
        _groupLoadFailed = true;
        _message = _i18n.t('approvals.genericError');
        _messageIsError = true;
      });
      debugPrint('Failed to load approval group: $e');
    } finally {
      if (mounted) setState(() => _groupLoading = false);
    }
  }

  String? _groupDecisionAction;
  String? _groupDecisionKey;

  @override
  void dispose() {
    _commentController.dispose();
    super.dispose();
  }

  Future<void> _submitDecision(PurchaseRequest request, String action) async {
    if (_submitting || _succeeded || _groupLoading || _groupLoadFailed) return;
    final comment = _commentController.text.trim();
    if (action == 'reject' && comment.isEmpty) {
      setState(() {
        _message = _i18n.t('approvals.decisionDialog.reasonRequired');
        _messageIsError = true;
      });
      return;
    }
    setState(() {
      _submitting = true;
      _message = null;
      _messageIsError = false;
    });

    try {
      final group = _group;
      if (group != null) {
        final client = ServiceProvider.of(context).approvalsApiClient;
        // One key per decision: a retry of the same action replays; switching action starts anew.
        if (_groupDecisionAction != action) {
          _groupDecisionAction = action;
          _groupDecisionKey = const Uuid().v4();
        }
        final key = _groupDecisionKey!;
        if (action == 'approve') {
          await client.approveGroup(
            group.summary.id,
            comment: comment,
            idempotencyKey: key,
          );
        } else {
          await client.rejectGroup(
            group.summary.id,
            comment: comment,
            idempotencyKey: key,
          );
        }
      } else if (action == 'approve') {
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
      final successText = _i18n.t(
        action == 'approve'
            ? 'approvals.approveSuccess'
            : 'approvals.rejectSuccess',
      );
      setState(() {
        _succeeded = true;
        _message = successText;
        _messageIsError = false;
      });
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(successText)));
      Navigator.of(context).pop(true);
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
    if (error.statusCode == 403) {
      return _i18n.t('approvals.notAssigned');
    }
    if (error.statusCode == 409 &&
        (error.details?['reason'] == 'no_pending_approval' ||
            error.details?['reason'] == 'not_submitted')) {
      return _i18n.t('approvals.alreadyDecided');
    }
    if (error.statusCode == 409 &&
        error.details?['reason'] == 'part_of_split') {
      return _i18n.t('approvals.partOfSplitError');
    }
    return _i18n.t('approvals.genericError');
  }

  @override
  Widget build(BuildContext context) {
    final args = ModalRoute.of(context)?.settings.arguments;
    final i18n = _i18n;
    final group = _group;
    final request = args is PurchaseRequest
        ? args
        : group != null && group.requests.isNotEmpty
        ? group.requests.first
        : null;
    if (request == null) {
      return Scaffold(
        appBar: AppBar(title: Text(i18n.t('approvals.title'))),
        body: Center(child: Text(i18n.t('approvals.notAvailable'))),
      );
    }

    final disabled =
        _submitting || _succeeded || _groupLoading || _groupLoadFailed;

    return Scaffold(
      appBar: AppBar(title: Text(i18n.t('approvals.title'))),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (group == null)
              RequestContextSection(request: request)
            else ...[
              _ApprovalGroupSection(group: group),
              if (_groupLoading)
                const Center(child: CircularProgressIndicator()),
            ],
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
              enabled: !disabled,
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
                    onPressed: _submitting || _succeeded
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
                    onPressed: disabled
                        ? null
                        : () => _submitDecision(request, 'approve'),
                    child: Text(i18n.t('approvals.actions.approve')),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            FilledButton.tonal(
              key: const Key('approvalDecisionRejectButton'),
              onPressed: disabled
                  ? null
                  : () => _submitDecision(request, 'reject'),
              child: Text(i18n.t('approvals.actions.reject')),
            ),
          ],
        ),
      ),
    );
  }
}

class _ApprovalGroupSection extends StatelessWidget {
  const _ApprovalGroupSection({required this.group});

  final ApprovalGroup group;

  @override
  Widget build(BuildContext context) {
    final i18n = ServiceProvider.of(context).i18n;
    final requests = [...group.requests]
      ..sort(
        (a, b) => a.requestGroup!.position.compareTo(b.requestGroup!.position),
      );
    String money(Money value) =>
        formatMoney(value.amount, value.currency, locale: i18n.locale);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          approvalGroupSummary(i18n, group.summary),
          key: const Key('approvalGroupSummary'),
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),
        RequestInfoRow(
          label: i18n.t('basketSplit.result.splitTotal'),
          value: money(group.summary.combinedTotal),
          valueStyle: LedgerTypography.tabularFigures(
            fontWeight: FontWeight.w600,
          ),
        ),
        for (final request in requests)
          Card(
            child: ExpansionTile(
              key: Key('approvalGroupRequest_${request.id}'),
              title: Text(
                request.source?.supplierName?.trim().isNotEmpty == true
                    ? request.source!.supplierName!.trim()
                    : i18n.t('rfq.history.unknownSupplier'),
              ),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    i18n.t(
                      'requests.split.siblingLink',
                      params: {'id': request.id},
                    ),
                  ),
                  if (request.budgetStatus != null) ...[
                    if (request.budgetStatus!.remainingAmount != null)
                      Text(
                        '${i18n.t('requests.budgetStatus.remainingLabel')}: ${money(request.budgetStatus!.remainingAmount!)}',
                      )
                    else ...[
                      Text(i18n.t('approvals.budgetStatus.no_budget')),
                      if (request.budgetStatus!.reasonCode != null)
                        Text(
                          i18n.t(
                            'approvals.budgetStatus.reasons.${request.budgetStatus!.reasonCode}',
                          ),
                        ),
                    ],
                    if (request.budgetStatus!.exceeds)
                      Text(
                        i18n.t('approvals.budgetExceeded'),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                  ],
                ],
              ),
              trailing: Text(
                request.estimatedTotal == null
                    ? i18n.t('approvals.notAvailable')
                    : money(request.estimatedTotal!),
                style: LedgerTypography.tabularFigures(),
              ),
              children: [
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: RequestContextSection(request: request),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
