import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/api/approvals_api_client.dart';
import '../../core/api/models.dart';
import '../../core/format/date_format.dart';
import '../../core/format/money_format.dart';
import '../../core/i18n/i18n_loader.dart';
import '../../core/theme/brand_logo.dart';
import '../../core/theme/ledger_typography.dart';
import '../service_provider.dart';
import 'approval_group.dart';

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
  String? _nextCursor;
  bool _loadingMore = false;
  String? _loadMoreError;
  int _loadGeneration = 0;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _loadApprovals();
  }

  Future<void> _loadApprovals() async {
    final generation = ++_loadGeneration;
    setState(() {
      _loading = true;
      _loadingMore = false;
      _loadMoreError = null;
    });
    try {
      final result = await _apiClient.listPendingApprovals(limit: 50);
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _requests = result.items;
        _nextCursor = result.nextCursor;
        _errorMessage = null;
      });
    } on Exception catch (e) {
      if (!mounted || generation != _loadGeneration) return;
      setState(() => _errorMessage = _i18n.t('approvals.genericError'));
      debugPrint('Failed to load pending approvals: $e');
    } finally {
      if (mounted && generation == _loadGeneration) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _loadMore() async {
    final cursor = _nextCursor;
    if (cursor == null || _loading || _loadingMore) return;
    final generation = _loadGeneration;
    setState(() {
      _loadingMore = true;
      _loadMoreError = null;
    });
    try {
      final result = await _apiClient.listPendingApprovals(
        cursor: cursor,
        limit: 50,
      );
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        final seenIds = _requests.map((request) => request.id).toSet();
        _requests = [
          ..._requests,
          ...result.items.where((request) => seenIds.add(request.id)),
        ];
        _nextCursor = result.nextCursor;
      });
    } on Exception catch (e) {
      if (!mounted || generation != _loadGeneration) return;
      setState(
        () => _loadMoreError = _i18n.t('approvals.pagination.loadError'),
      );
      debugPrint('Failed to load more pending approvals: $e');
    } finally {
      if (mounted && generation == _loadGeneration) {
        setState(() => _loadingMore = false);
      }
    }
  }

  String _paginationStatusText() {
    final category = Intl.pluralLogic(
      _requests.length,
      locale: _i18n.locale,
      zero: 'zero',
      one: 'one',
      two: 'two',
      few: 'few',
      many: 'many',
      other: 'other',
    );
    final status = _nextCursor == null ? 'showing' : 'showingMore';
    return _i18n.t(
      'approvals.pagination.$status.$category',
      params: {'count': _requests.length.toString()},
    );
  }

  Widget _paginationFooter() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          Semantics(
            liveRegion: true,
            child: Text(
              _paginationStatusText(),
              key: const Key('approvalQueueStatus'),
              textAlign: TextAlign.center,
            ),
          ),
          if (_loadMoreError != null) ...[
            const SizedBox(height: 8),
            Semantics(
              liveRegion: true,
              child: Text(
                _loadMoreError!,
                textAlign: TextAlign.center,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          ],
          if (_nextCursor != null) ...[
            const SizedBox(height: 8),
            FilledButton.tonal(
              key: const Key('approvalQueueLoadMore'),
              onPressed: _loadingMore ? null : _loadMore,
              child: Wrap(
                alignment: WrapAlignment.center,
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 8,
                children: [
                  if (_loadingMore)
                    const SizedBox.square(
                      dimension: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  Text(
                    _i18n.t(
                      _loadingMore
                          ? 'approvals.pagination.loading'
                          : 'approvals.pagination.loadMore',
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _navigateToDecision(Object request) async {
    final result = await Navigator.of(context)
        .pushNamed('/approvals/detail', arguments: request);
    if (result == true && mounted) {
      await _loadApprovals();
    }
  }

  @override
  Widget build(BuildContext context) {
    final i18n = _i18n;
    final entries = <List<PurchaseRequest>>[];
    final groups = <String, List<PurchaseRequest>>{};
    for (final request in _requests) {
      final group = request.requestGroup;
      if (group == null) {
        entries.add([request]);
      } else {
        final members = groups.putIfAbsent(group.id, () {
          final members = <PurchaseRequest>[];
          entries.add(members);
          return members;
        });
        members.add(request);
      }
    }
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
                      itemCount: entries.length + 1,
                      itemBuilder: (context, index) {
                        if (index == entries.length) {
                          return _paginationFooter();
                        }
                        final requests = entries[index];
                        final request = requests.first;
                        final group = request.requestGroup;
                        if (group != null) {
                          return ListTile(
                            key: Key('approvalQueueItem_$index'),
                            title: Text(approvalGroupSummary(i18n, group)),
                            onTap: () => _navigateToDecision(
                              ApprovalGroup(summary: group, requests: requests),
                            ),
                          );
                        }
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
