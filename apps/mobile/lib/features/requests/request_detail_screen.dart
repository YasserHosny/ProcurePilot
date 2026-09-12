import 'package:flutter/material.dart';

import '../../core/api/models.dart';
import '../../core/i18n/i18n_loader.dart';
import '../service_provider.dart';

/// Read-only purchase-request detail screen.
///
/// Renders the request's lines and, when present, its [approval_step]
/// exactly like the web form's existing approval-step block:
/// a status chip, assigned-to, and — once decided — the approver's comment
/// and decision timestamp. No approve/reject controls are rendered (FR-009).
class RequestDetailScreen extends StatelessWidget {
  const RequestDetailScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final args = ModalRoute.of(context)?.settings.arguments;
    final PurchaseRequest req;
    if (args is PurchaseRequest) {
      req = args;
    } else if (args is String) {
      // A request id may be passed for deep-link-style navigation; this screen
      // currently shows the provided object. Full id-based loading is left for
      // the notification deep-link work in Phase 6.
      return Scaffold(
        appBar: AppBar(title: Text(_i18n(context).t('requests.title'))),
        body: const Center(child: CircularProgressIndicator()),
      );
    } else {
      return Scaffold(
        appBar: AppBar(title: Text(_i18n(context).t('requests.title'))),
        body: const Center(child: Text('Request not found')),
      );
    }

    final i18n = _i18n(context);
    final step = req.approvalStep;

    return Scaffold(
      appBar: AppBar(title: Text(i18n.t('requests.title'))),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _InfoRow(
              label: i18n.t('requests.columns.requiredByDate'),
              value: req.requiredByDate,
            ),
            _InfoRow(
              label: i18n.t('requests.columns.status'),
              value: i18n.t('requests.status.${req.status}'),
            ),
            if (req.estimatedTotal != null)
              _InfoRow(
                label: i18n.t('requests.columns.estimatedTotal'),
                value:
                    '${req.estimatedTotal!.currency} ${req.estimatedTotal!.amount}',
              ),
            if (req.hasIncompleteEstimate)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Chip(
                  label: Text(i18n.t('requests.incompleteEstimateBadge')),
                ),
              ),
            const Divider(),
            Text(
              i18n.t('requests.form.linesTitle'),
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            ...req.lines.asMap().entries.map((entry) {
              final line = entry.value;
              return Card(
                child: ListTile(
                  key: Key('requestDetailLine_${entry.key}'),
                  title: Text(line.workspaceProductId),
                  subtitle: Text(
                    '${i18n.t('requests.form.quantityLabel')}: ${line.quantity}',
                  ),
                  trailing:
                      line.estimatedUnitPrice != null
                          ? Text(
                            '${line.estimatedUnitPrice!.currency} ${line.estimatedUnitPrice!.amount}',
                          )
                          : null,
                ),
              );
            }),
            if (step != null) ...[
              const Divider(),
              Text(
                i18n.t('requests.approval.sectionTitle'),
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Chip(
                key: Key('approvalStepStatus_${step.status}'),
                label: Text(i18n.t('requests.status.${step.status}')),
              ),
              _InfoRow(
                label: i18n.t('requests.approval.assignedTo'),
                value: step.assignedMembershipId,
              ),
              if (step.status != 'pending') ...[
                if (step.comment != null)
                  _InfoRow(
                    label: i18n.t('requests.approval.comment'),
                    value: step.comment!,
                  ),
                if (step.decidedAt != null)
                  _InfoRow(
                    label: i18n.t('requests.approval.decidedAt'),
                    value: step.decidedAt!.toIso8601String(),
                  ),
              ] else
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Text(i18n.t('requests.approval.pending')),
                ),
            ],
          ],
        ),
      ),
    );
  }

  I18nLoader _i18n(BuildContext context) =>
      ServiceProvider.of(context).i18n;
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$label: ', style: const TextStyle(fontWeight: FontWeight.bold)),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
