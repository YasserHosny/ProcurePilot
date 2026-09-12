import 'package:flutter/material.dart';

import '../../core/api/models.dart';
import '../../core/api/requests_api_client.dart';
import '../../core/i18n/i18n_loader.dart';
import '../service_provider.dart';

/// Lists the signed-in member's own purchase requests with status filtering.
class RequestListScreen extends StatefulWidget {
  const RequestListScreen({super.key});

  @override
  State<RequestListScreen> createState() => _RequestListScreenState();
}

class _RequestListScreenState extends State<RequestListScreen> {
  RequestsApiClient get _apiClient =>
      ServiceProvider.of(context).requestsApiClient;
  I18nLoader get _i18n => ServiceProvider.of(context).i18n;

  List<PurchaseRequest> _requests = [];
  bool _loading = false;
  String? _errorMessage;
  String _statusFilter = '';

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _loadRequests();
  }

  Future<void> _loadRequests() async {
    setState(() => _loading = true);
    try {
      final result = await _apiClient.listRequests(
        status: _statusFilter.isEmpty ? null : _statusFilter,
      );
      if (!mounted) return;
      setState(() {
        _requests = result.items;
        _errorMessage = null;
      });
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() => _errorMessage = _i18n.t('requests.genericError'));
      debugPrint('Failed to load requests: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _onFilterChanged(String? value) {
    setState(() => _statusFilter = value ?? '');
    _loadRequests();
  }

  void _navigateToDetail(PurchaseRequest req) {
    Navigator.of(context).pushNamed('/requests/detail', arguments: req);
  }

  @override
  Widget build(BuildContext context) {
    final i18n = _i18n;
    return Scaffold(
      appBar: AppBar(
        title: Text(i18n.t('requests.title')),
        actions: [
          IconButton(
            key: const Key('requestListNewRequestButton'),
            icon: const Icon(Icons.add),
            tooltip: i18n.t('requests.form.createTitle'),
            onPressed: () => Navigator.of(context).pushNamed('/requests/new'),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(12),
              child: FormField<String>(
                key: const Key('requestListStatusFilter'),
                builder: (field) {
                  return InputDecorator(
                    decoration: InputDecoration(
                      labelText: i18n.t('requests.columns.status'),
                      errorText: field.errorText,
                    ),
                    child: DropdownButtonHideUnderline(
                      child: DropdownButton<String>(
                        value: _statusFilter.isEmpty ? null : _statusFilter,
                        isDense: true,
                        items: [
                          DropdownMenuItem(
                            value: '',
                            child: Text(i18n.t('common.all')),
                          ),
                          ...[
                            'draft',
                            'submitted',
                            'approved',
                            'rejected',
                            'withdrawn',
                          ].map(
                            (status) => DropdownMenuItem(
                              value: status,
                              child: Text(i18n.t('requests.status.$status')),
                            ),
                          ),
                        ],
                        onChanged: (value) {
                          field.didChange(value);
                          _onFilterChanged(value);
                        },
                      ),
                    ),
                  );
                },
              ),
            ),
            if (_errorMessage != null)
              Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  _errorMessage!,
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.error,
                  ),
                ),
              ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : _requests.isEmpty
                      ? Center(child: Text(i18n.t('requests.empty')))
                      : ListView.builder(
                          key: const Key('requestList'),
                          itemCount: _requests.length,
                          itemBuilder: (context, index) {
                            final req = _requests[index];
                            return ListTile(
                              key: Key('requestListItem_$index'),
                              title: Text(
                                '${i18n.t('requests.columns.requiredByDate')}: ${req.requiredByDate}',
                              ),
                              subtitle: _statusChip(req.status),
                              trailing: _moneyText(req.estimatedTotal),
                              onTap: () => _navigateToDetail(req),
                            );
                          },
                        ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _statusChip(String status) {
    return Chip(
      key: Key('requestStatus_$status'),
      label: Text(_i18n.t('requests.status.$status')),
    );
  }

  Widget? _moneyText(Money? money) {
    if (money == null) return null;
    return Text('${money.currency} ${money.amount}');
  }
}
