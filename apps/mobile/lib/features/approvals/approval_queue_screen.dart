import 'package:flutter/material.dart';

import '../../core/api/approvals_api_client.dart';
import '../../core/api/models.dart';
import '../../core/i18n/i18n_loader.dart';
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

  void _navigateToDecision(PurchaseRequest request) {
    Navigator.of(context).pushNamed('/approvals/detail', arguments: request);
  }

  @override
  Widget build(BuildContext context) {
    final i18n = _i18n;
    return Scaffold(
      appBar: AppBar(title: Text(i18n.t('approvals.title'))),
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
                            '${request.requestedByMembershipId}',
                          ),
                          subtitle: Text(
                            '${i18n.t('approvals.columns.requiredByDate')}: '
                            '${request.requiredByDate}',
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
    return Text('${money.currency} ${money.amount}');
  }
}
