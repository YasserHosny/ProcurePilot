import 'dart:async';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../core/api/mobile_api_client.dart';
import '../../core/api/models.dart';
import '../../core/api/requests_api_client.dart';
import '../../core/i18n/i18n_loader.dart';
import '../../core/offline_queue/offline_queue_service.dart';
import '../../core/offline_queue/status_widgets.dart';
import '../service_provider.dart';

/// Low-stock report screen (User Story 3 / T032).
///
/// Records a fast "shelf is running low" signal unlinked to any purchase
/// request (FR-006). Uses [RequestsApiClient.searchCatalogue] and
/// [RequestsApiClient.listBranches] for product and branch selection, and
/// [MobileApiClient.createLowStockReport] to record the report.
///
/// Stamping of [idempotencyKey] is done client-side once per submission tap,
/// and reused on retry (FR-011). Double-taps are debounced client-side via a
/// submitting guard.
class LowStockReportScreen extends StatefulWidget {
  const LowStockReportScreen({
    super.key,
    this.initialProduct,
    this.initialBranchId,
    this.offlineQueueService,
  });

  final CatalogueProduct? initialProduct;
  final String? initialBranchId;
  final OfflineQueue? offlineQueueService;

  @override
  State<LowStockReportScreen> createState() => _LowStockReportScreenState();
}

class _LowStockReportScreenState extends State<LowStockReportScreen> {
  MobileApiClient get _mobileApiClient =>
      ServiceProvider.of(context).mobileApiClient;
  RequestsApiClient get _requestsApiClient =>
      ServiceProvider.of(context).requestsApiClient;
  I18nLoader get _i18n => ServiceProvider.of(context).i18n;
  OfflineQueue? get _offlineQueue =>
      widget.offlineQueueService ??
      ServiceProvider.of(context).offlineQueueService;

  final _formKey = GlobalKey<FormState>();
  final _searchController = TextEditingController();
  final _countRemainingController = TextEditingController();

  CatalogueProduct? _selectedProduct;
  String? _selectedProductId;
  String? _branchId;
  List<Branch> _branches = [];
  bool _loadingMeta = false;

  Timer? _searchDebounce;
  List<CatalogueProduct> _catalogueResults = [];
  bool _catalogueLoading = false;

  bool _submitting = false;
  String? _idempotencyKey;
  LowStockReport? _submittedReport;
  bool _submittedReportQueued = false;

  String? _errorMessage;
  String? _productError;
  String? _branchError;

  @override
  void initState() {
    super.initState();
    if (widget.initialProduct != null) {
      _selectedProduct = widget.initialProduct;
      _selectedProductId = widget.initialProduct!.id;
      _searchController.text = widget.initialProduct!.tenantName;
    }
    if (widget.initialBranchId != null) {
      _branchId = widget.initialBranchId;
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_branches.isEmpty && !_loadingMeta) {
      _loadMeta();
    }
    if (_selectedProduct == null) {
      final args = ModalRoute.of(context)?.settings.arguments;
      if (args is CatalogueProduct) {
        _selectedProduct = args;
        _selectedProductId = args.id;
        _searchController.text = args.tenantName;
      } else if (args is Map<String, dynamic>) {
        if (args['product'] is CatalogueProduct) {
          final product = args['product'] as CatalogueProduct;
          _selectedProduct = product;
          _selectedProductId = product.id;
          _searchController.text = product.tenantName;
        }
        if (args['branchId'] is String && _branchId == null) {
          _branchId = args['branchId'] as String;
        }
      }
    }
  }

  Future<void> _loadMeta() async {
    setState(() => _loadingMeta = true);
    try {
      final branches = await _requestsApiClient.listBranches();
      if (!mounted) return;
      setState(() {
        _branches = branches.items;
        if (_branches.length == 1 && _branchId == null) {
          _branchId = _branches.first.id;
        }
      });
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() => _errorMessage = _i18n.t('requests.genericError'));
      debugPrint('Failed to load branches: $e');
    } finally {
      if (mounted) setState(() => _loadingMeta = false);
    }
  }

  void _onCatalogueSearch(String query) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 300), () async {
      if (!mounted) return;
      final trimmed = query.trim();
      if (trimmed.length < 2) {
        setState(() => _catalogueResults = []);
        return;
      }
      setState(() => _catalogueLoading = true);
      try {
        final result = await _requestsApiClient.searchCatalogue(query: trimmed);
        if (!mounted) return;
        setState(() => _catalogueResults = result.items);
      } on Exception catch (e) {
        debugPrint('Catalogue search failed: $e');
      } finally {
        if (mounted) setState(() => _catalogueLoading = false);
      }
    });
  }

  void _selectProduct(CatalogueProduct product) {
    setState(() {
      _selectedProduct = product;
      _selectedProductId = product.id;
      _productError = null;
      _catalogueResults = [];
      _searchController.text = product.tenantName;
    });
  }

  void _clearProduct() {
    setState(() {
      _selectedProduct = null;
      _selectedProductId = null;
      _searchController.clear();
      _catalogueResults = [];
      _idempotencyKey = null;
    });
  }

  String? _countRemainingValidator(String? value) {
    if (value == null || value.trim().isEmpty) {
      return null;
    }
    final trimmed = value.trim();
    if (!RegExp(r'^[0-9]+(\.[0-9]+)?$').hasMatch(trimmed)) {
      return _i18n.t('requests.form.quantityRequired');
    }
    return null;
  }

  Future<void> _submit() async {
    if (_submitting || _submittedReport != null) return;

    final productId = _selectedProductId ?? _selectedProduct?.id;
    var hasError = false;
    if (productId == null || productId.isEmpty) {
      setState(() => _productError = _i18n.t('requests.form.productRequired'));
      hasError = true;
    } else {
      setState(() => _productError = null);
    }

    if (_branchId == null || _branchId!.isEmpty) {
      setState(() => _branchError = _i18n.t('requests.form.branchRequired'));
      hasError = true;
    } else {
      setState(() => _branchError = null);
    }

    if (!_formKey.currentState!.validate()) {
      hasError = true;
    }

    if (hasError) return;

    setState(() {
      _submitting = true;
      _errorMessage = null;
    });

    _idempotencyKey ??= const Uuid().v4();
    final key = _idempotencyKey!;

    final countText = _countRemainingController.text.trim();
    final String? countRemaining = countText.isEmpty ? null : countText;

    try {
      final report = await _mobileApiClient.createLowStockReport(
        branchId: _branchId!,
        workspaceProductId: productId!,
        countRemaining: countRemaining,
        idempotencyKey: key,
      );
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _submittedReport = report;
        _submittedReportQueued = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.message;
        _submitting = false;
      });
    } on Exception catch (e) {
      final queued = await _queueLowStockReport(
        branchId: _branchId!,
        workspaceProductId: productId!,
        countRemaining: countRemaining,
      );
      if (!mounted) return;
      if (queued) {
        setState(() {
          _submitting = false;
          _submittedReport = LowStockReport(
            id: key,
            branchId: _branchId!,
            memberId: '',
            workspaceProductId: productId,
            countRemaining: countRemaining,
            createdAt: DateTime.now(),
          );
          _submittedReportQueued = true;
        });
        return;
      }
      setState(() {
        _errorMessage = _i18n.t('requests.genericError');
        _submitting = false;
      });
      debugPrint('Low-stock report submission failed: $e');
    }
  }

  Future<bool> _queueLowStockReport({
    required String branchId,
    required String workspaceProductId,
    required String? countRemaining,
  }) async {
    final queue = _offlineQueue;
    if (queue == null) return false;
    await queue.createAndEnqueue(
      endpoint: 'low-stock-reports',
      payload: {
        'branch_id': branchId,
        'workspace_product_id': workspaceProductId,
        'count_remaining': countRemaining,
      },
      idempotencyKey: _idempotencyKey,
    );
    return true;
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _searchController.dispose();
    _countRemainingController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final i18n = _i18n;

    if (_submittedReport != null) {
      return Scaffold(
        appBar: AppBar(title: Text(i18n.t('lowStock.title'))),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              key: const Key('lowStockConfirmationView'),
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_submittedReportQueued)
                  SubmissionQueuedBanner(
                    message: i18n.t('lowStock.queuedMessage'),
                  )
                else
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Icon(
                        Icons.check_circle_outline,
                        key: Key('lowStockSuccessIcon'),
                        color: Colors.green,
                        size: 64,
                      ),
                      const SizedBox(height: 16),
                      Text(
                        i18n.t('lowStock.submittedMessage'),
                        key: const Key('lowStockSubmittedMessage'),
                        style: Theme.of(context).textTheme.titleLarge,
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                if (_submittedReport!.countRemaining != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    '${i18n.t('lowStock.countRemainingLabel')}: ${_submittedReport!.countRemaining}',
                    key: const Key('lowStockConfirmationCount'),
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ],
                const SizedBox(height: 24),
                OutlinedButton(
                  key: const Key('lowStockDoneButton'),
                  onPressed: () {
                    if (Navigator.of(context).canPop()) {
                      Navigator.of(context).pop();
                    } else {
                      setState(() {
                        _submittedReport = null;
                        _idempotencyKey = null;
                        _countRemainingController.clear();
                      });
                    }
                  },
                  child: Text(i18n.t('requests.form.cancelButton')),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: Text(i18n.t('lowStock.title'))),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_errorMessage != null)
                  Card(
                    key: const Key('lowStockErrorCard'),
                    color: Theme.of(context).colorScheme.errorContainer,
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Text(
                        _errorMessage!,
                        key: const Key('lowStockErrorMessage'),
                      ),
                    ),
                  ),
                if (_selectedProduct != null)
                  Card(
                    key: const Key('lowStockSelectedProductCard'),
                    child: ListTile(
                      title: Text(
                        _selectedProduct!.tenantName,
                        key: const Key('lowStockSelectedProductName'),
                      ),
                      subtitle: Text(_selectedProduct!.baseUnit),
                      trailing: IconButton(
                        key: const Key('lowStockClearProductButton'),
                        icon: const Icon(Icons.close),
                        tooltip: i18n.t('requests.form.removeLineButton'),
                        onPressed: _clearProduct,
                      ),
                    ),
                  )
                else ...[
                  TextFormField(
                    key: const Key('lowStockProductSearchField'),
                    controller: _searchController,
                    decoration: InputDecoration(
                      labelText: i18n.t('requests.form.productLabel'),
                      hintText: i18n.t('mobileRequests.productSearchHint'),
                      errorText: _productError,
                      prefixIcon: const Icon(Icons.search),
                    ),
                    onChanged: _onCatalogueSearch,
                  ),
                  if (_catalogueLoading)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: Center(
                        child: CircularProgressIndicator(
                          key: Key('lowStockProductLoading'),
                        ),
                      ),
                    )
                  else if (_catalogueResults.isNotEmpty)
                    SizedBox(
                      height: 140,
                      child: ListView.builder(
                        key: const Key('lowStockProductResults'),
                        itemCount: _catalogueResults.length,
                        itemBuilder: (context, index) {
                          final product = _catalogueResults[index];
                          return ListTile(
                            key: Key('lowStockProductResult_$index'),
                            title: Text(product.tenantName),
                            subtitle: Text(product.baseUnit),
                            onTap: () => _selectProduct(product),
                          );
                        },
                      ),
                    ),
                ],
                const SizedBox(height: 16),
                InputDecorator(
                  key: const Key('lowStockBranchField'),
                  decoration: InputDecoration(
                    labelText: i18n.t('requests.form.branchLabel'),
                    errorText: _branchError,
                  ),
                  child: DropdownButtonHideUnderline(
                    child: DropdownButton<String>(
                      value: _branchId,
                      hint: Text(i18n.t('requests.form.branchLabel')),
                      items: _branches
                          .map(
                            (b) => DropdownMenuItem(
                              value: b.id,
                              child: Text(b.name),
                            ),
                          )
                          .toList(),
                      onChanged: (value) {
                        setState(() {
                          _branchId = value;
                          _branchError = null;
                        });
                      },
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                TextFormField(
                  key: const Key('lowStockCountRemainingField'),
                  controller: _countRemainingController,
                  decoration: InputDecoration(
                    labelText: i18n.t('lowStock.countRemainingLabel'),
                    hintText: '0',
                  ),
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  validator: _countRemainingValidator,
                ),
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        key: const Key('lowStockCancelButton'),
                        onPressed: () {
                          if (Navigator.of(context).canPop()) {
                            Navigator.of(context).pop();
                          }
                        },
                        child: Text(i18n.t('requests.form.cancelButton')),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: ElevatedButton(
                        key: const Key('lowStockSubmitButton'),
                        onPressed: (_submitting || _submittedReport != null)
                            ? null
                            : _submit,
                        child: Text(
                          _submitting
                              ? i18n.t('requests.form.submittingButton')
                              : i18n.t('lowStock.actionLabel'),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
