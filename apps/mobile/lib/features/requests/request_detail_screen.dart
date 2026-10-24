import 'package:flutter/material.dart';

import '../../core/api/models.dart';
import '../../core/i18n/i18n_loader.dart';
import '../../core/format/money_format.dart';
import '../../core/format/quantity_format.dart';
import '../../core/theme/ledger_typography.dart';
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
    return Scaffold(
      appBar: AppBar(title: Text(i18n.t('requests.title'))),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            RequestContextSection(request: req),
            if (req.status == 'ordered') ...[
              const SizedBox(height: 16),
              FilledButton(
                key: const Key('requestConfirmDeliveryButton'),
                onPressed: () {
                  Navigator.of(context)
                      .pushNamed('/delivery/confirm', arguments: req);
                },
                child: Text(i18n.t('delivery.entryPointButton')),
              ),
            ],
            if (req.status == 'delivered') ...[
              const SizedBox(height: 16),
              FilledButton(
                key: const Key('requestQualityIssueButton'),
                onPressed: () {
                  Navigator.of(context)
                      .pushNamed('/delivery/qualityIssue', arguments: req);
                },
                child: Text(i18n.t('qualityIssue.entryPointButton')),
              ),
            ],
            RequestApprovalStepSection(request: req),
          ],
        ),
      ),
    );
  }

  I18nLoader _i18n(BuildContext context) => ServiceProvider.of(context).i18n;
}

class RequestContextSection extends StatelessWidget {
  const RequestContextSection({super.key, required this.request});

  final PurchaseRequest request;

  @override
  Widget build(BuildContext context) {
    final i18n = ServiceProvider.of(context).i18n;
    final autoPrepared = request.autoPrepared;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (autoPrepared != null)
          _AutoPreparedBanner(request: request, provenance: autoPrepared),
        RequestInfoRow(
          label: i18n.t('requests.columns.requiredByDate'),
          value: request.requiredByDate,
        ),
        RequestInfoRow(
          label: i18n.t('requests.columns.status'),
          value: i18n.t('requests.status.${request.status}'),
        ),
        RequestInfoRow(
          label: i18n.t('approvals.columns.requester'),
          value: request.requesterDisplayName(i18n),
        ),
        if (request.estimatedTotal != null)
          RequestInfoRow(
            label: i18n.t('requests.columns.estimatedTotal'),
            value: _formatMoney(i18n, request.estimatedTotal!),
            valueStyle: LedgerTypography.tabularFigures(),
          ),
        if (request.budgetStatus != null) ...[
          RequestInfoRow(
            label: i18n.t('requests.budgetStatus.remainingLabel'),
            value: _formatMoney(i18n, request.budgetStatus!.remainingAmount),
            valueStyle: LedgerTypography.tabularFigures(),
          ),
          if (request.budgetStatus!.exceeds)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Chip(
                key: const Key('requestBudgetExceeded'),
                label: Text(i18n.t('requests.budgetStatus.exceedsWarning')),
              ),
            ),
        ],
        if (request.hasIncompleteEstimate)
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
        ...request.lines.asMap().entries.map((entry) {
          final line = entry.value;
          final formattedQty = formatQuantity(
            line.quantity,
            packBaseQuantity: line.packBaseQuantity,
            baseUnit: line.baseUnit,
            locale: i18n.locale,
            i18n: i18n,
          );
          final subtitleLines = [
            '${i18n.t('requests.form.quantityLabel')}: $formattedQty',
            if (line.quantityReceived != null)
              '${i18n.t('delivery.quantityReceivedLabel')}: ${formatQuantity(
                line.quantityReceived!,
                packBaseQuantity: line.packBaseQuantity,
                baseUnit: line.baseUnit,
                locale: i18n.locale,
                i18n: i18n,
              )}',
          ];
          return Card(
            child: ListTile(
              key: Key('requestDetailLine_${entry.key}'),
              title: Text(line.productDisplayName(i18n)),
              subtitle: Text(subtitleLines.join('\n')),
              trailing: line.estimatedUnitPrice != null
                  ? Text(
                      _formatMoney(i18n, line.estimatedUnitPrice!),
                      style: LedgerTypography.tabularFigures(),
                    )
                  : null,
            ),
          );
        }),
      ],
    );
  }
}

String _formatMoney(I18nLoader i18n, Money money) =>
    formatMoney(money.amount, money.currency, locale: i18n.locale);

class RequestApprovalStepSection extends StatelessWidget {
  const RequestApprovalStepSection({super.key, required this.request});

  final PurchaseRequest request;

  @override
  Widget build(BuildContext context) {
    final step = request.approvalStep;
    if (step == null) return const SizedBox.shrink();

    final i18n = ServiceProvider.of(context).i18n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
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
        RequestInfoRow(
          label: i18n.t('requests.approval.assignedTo'),
          value: step.assignedMembershipId,
        ),
        if (step.status != 'pending') ...[
          if (step.comment != null)
            RequestInfoRow(
              label: i18n.t('requests.approval.comment'),
              value: step.comment!,
            ),
          if (step.decidedAt != null)
            RequestInfoRow(
              label: i18n.t('requests.approval.decidedAt'),
              value: step.decidedAt!.toIso8601String(),
            ),
        ] else
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(i18n.t('requests.approval.pending')),
          ),
      ],
    );
  }
}

class RequestInfoRow extends StatelessWidget {
  const RequestInfoRow({
    super.key,
    required this.label,
    required this.value,
    this.valueStyle,
  });

  final String label;
  final String value;
  final TextStyle? valueStyle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$label: ', style: const TextStyle(fontWeight: FontWeight.bold)),
          Expanded(child: Text(value, style: valueStyle)),
        ],
      ),
    );
  }
}

/// Says that a guardrail, not a person, drafted the request, and from whose quote.
class _AutoPreparedBanner extends StatelessWidget {
  const _AutoPreparedBanner({required this.request, required this.provenance});

  final PurchaseRequest request;
  final AutoPreparedProvenance provenance;

  @override
  Widget build(BuildContext context) {
    final i18n = ServiceProvider.of(context).i18n;
    final scheme = Theme.of(context).colorScheme;
    final supplier = provenance.supplierName?.trim().isNotEmpty == true
        ? provenance.supplierName!.trim()
        : i18n.t('requests.autoPrepared.unknownSupplier');
    final messageKey = request.status == 'draft'
        ? 'requests.autoPrepared.draftMessage'
        : 'requests.autoPrepared.message';
    return Card(
      key: const Key('requestAutoPreparedBanner'),
      color: scheme.secondaryContainer,
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsetsDirectional.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.smart_toy_outlined, color: scheme.onSecondaryContainer),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    i18n.t('requests.autoPrepared.title'),
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          color: scheme.onSecondaryContainer,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    i18n.t(messageKey, params: {'supplier': supplier}),
                    style: TextStyle(color: scheme.onSecondaryContainer),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
