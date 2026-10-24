import 'package:flutter/material.dart';

import '../../core/api/approvals_api_client.dart';
import '../../core/api/models.dart';
import '../../core/format/date_format.dart';
import '../../core/format/money_format.dart';
import '../../core/i18n/i18n_loader.dart';
import '../../core/theme/brand_logo.dart';
import '../../core/theme/ledger_typography.dart';
import '../service_provider.dart';

class ApprovalQueueScreen extends StatefulWidget {
  const ApprovalQueueScreen({super.key});

  @override
  State<ApprovalQueueScreen> createState() => _ApprovalQueueScreenState();
}

class _ApprovalQueueScreenState extends State<ApprovalQueueScreen> {
  ApprovalsApiClient get _apiClient =>
      ServiceProvider.of(context).approvalsApiClient;
  I18nLoader get _i18n => ServiceProvider.of(context).i18n;

  List<PurchaseRequest> _requests = [];
  bool _loading = false;
  String? _errorMessage;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _loadApprovals();
  }

  Future<void> _loadApprovals() async {
    setState(() => _loading = true);
    try {
      final result = await _apiClient.listPendingApprovals();
      if (!mounted) return;
      setState(() {
        _requests = result.items;
        _errorMessage = null;
      });
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() => _errorMessage = _i18n.t('approvals.genericError'));
      debugPrint('Failed to load pending approvals: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _navigateToDecision(PurchaseRequest request) async {
    final result = await Navigator.of(context).pushNamed(
      '/approvals/detail',
      arguments: request,
    );
    if (result == true && mounted) {
      await _loadApprovals();
    }
  }

  @override
  Widget build(BuildContext context) {
    final i18n = _i18n;
    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const BrandLogo(height: 28),
            const SizedBox(width: 8),
            Flexible(
              child: Text(
                i18n.t('approvals.title'),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (_errorMessage != null)
              Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  _errorMessage!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : _requests.isEmpty
                  ? Center(child: Text(i18n.t('approvals.empty')))
                  : ListView.builder(
                      key: const Key('approvalQueueList'),
                      itemCount: _requests.length,
                      itemBuilder: (context, index) {
                        final request = _requests[index];
                        return ListTile(
                          key: Key('approvalQueueItem_$index'),
                          title: Text(
                            '${i18n.t('approvals.columns.requester')}: '
                            '${request.requesterDisplayName(i18n)}',
                          ),
                          subtitle: Text(
                            '${i18n.t('approvals.columns.requiredByDate')}: '
                            '${formatDate(request.requiredByDate, locale: _i18n.locale)}',
                          ),
                          trailing: _moneyText(request.estimatedTotal),
                          onTap: () => _navigateToDecision(request),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget? _moneyText(Money? money) {
    if (money == null) return null;
    return Text(
      formatMoney(money.amount, money.currency, locale: _i18n.locale),
      style: LedgerTypography.tabularFigures(fontWeight: FontWeight.w600),
    );
  }
}
