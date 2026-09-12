import 'dart:async';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../core/api/models.dart';
import '../../core/api/requests_api_client.dart';
import '../../core/i18n/i18n_loader.dart';
import '../../core/offline_queue/offline_queue_service.dart';
import '../../core/offline_queue/status_widgets.dart';
import '../service_provider.dart';

/// Purchase-request form screen.
///
/// Creates a draft via [POST /requests] on first save, then patches the same
/// draft via [PATCH /requests/{id}] for subsequent edits. Submission goes
/// through [POST /requests/{id}/submit].
class RequestFormScreen extends StatefulWidget {
  const RequestFormScreen({super.key, this.offlineQueueService});

  final OfflineQueue? offlineQueueService;

  @override
  State<RequestFormScreen> createState() => _RequestFormScreenState();
}

class _LineInput {
  _LineInput({
    required this.workspaceProductId,
    required this.quantity,
    this.note,
  });

  String workspaceProductId;
  String quantity;
  String? note;
}

class _RequestFormScreenState extends State<RequestFormScreen> {
  RequestsApiClient get _apiClient =>
      ServiceProvider.of(context).requestsApiClient;
  OfflineQueue? get _offlineQueue =>
      widget.offlineQueueService ??
      ServiceProvider.of(context).offlineQueueService;
  I18nLoader get _i18n => ServiceProvider.of(context).i18n;

  final _formKey = GlobalKey<FormState>();
  String? _branchId;
  String? _costCentreId;
  final List<_LineInput> _lines = [];

  List<Branch> _branches = [];
  List<CostCentre> _costCentres = [];
  bool _loadingMeta = false;

  PurchaseRequest? _savedRequest;
  String? _offlineSubmitIdempotencyKey;
  bool _saving = false;
  bool _submitting = false;
  bool _submissionQueued = false;
  String? _errorMessage;
  String? _branchError;

  Timer? _searchDebounce;
  List<CatalogueProduct> _catalogueResults = [];
  bool _catalogueLoading = false;

  @override
  void initState() {
    super.initState();
    _addLine();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_branches.isEmpty && !_loadingMeta) {
      _loadMeta();
    }
  }

  Future<void> _loadMeta() async {
    setState(() => _loadingMeta = true);
    try {
      final branches = await _apiClient.listBranches();
      final costCentres = await _apiClient.listCostCentres();
      if (!mounted) return;
      setState(() {
        _branches = branches.items;
        _costCentres = costCentres.items;
      });
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() => _errorMessage = _i18n.t('requests.genericError'));
      debugPrint('Failed to load form metadata: $e');
    } finally {
      if (mounted) setState(() => _loadingMeta = false);
    }
  }

  void _addLine() {
    setState(() {
      _lines.add(_LineInput(workspaceProductId: '', quantity: '', note: null));
    });
  }

  void _removeLine(int index) {
    setState(() => _lines.removeAt(index));
  }

  Future<void> _onCatalogueSearch(String query, int lineIndex) async {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 300), () async {
      if (!mounted) return;
      if (query.length < 2) {
        setState(() => _catalogueResults = []);
        return;
      }
      setState(() => _catalogueLoading = true);
      try {
        final result = await _apiClient.searchCatalogue(query: query);
        if (!mounted) return;
        setState(() => _catalogueResults = result.items);
      } on Exception catch (e) {
        debugPrint('Catalogue search failed: $e');
      } finally {
        if (mounted) setState(() => _catalogueLoading = false);
      }
    });
  }

  Future<void> _saveDraft() async {
    setState(() => _branchError = null);
    if (!_formKey.currentState!.validate()) return;
    if (_branchId == null || _branchId!.isEmpty) {
      setState(() => _branchError = _i18n.t('requests.form.branchRequired'));
      return;
    }
    if (_lines.isEmpty) return;

    _formKey.currentState!.save();
    setState(() {
      _saving = true;
      _errorMessage = null;
    });

    final body = _requestBody();

    try {
      final saved = _savedRequest == null
          ? await _apiClient.createRequest(body)
          : await _apiClient.updateRequest(
              _savedRequest!.id,
              PurchaseRequestUpdate(
                branchId: body.branchId,
                costCentreId: body.costCentreId,
                requiredByDate: body.requiredByDate,
                lines: body.lines,
              ),
            );
      if (!mounted) return;
      setState(() {
        _savedRequest = saved;
        _saving = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_i18n.t('requests.createSuccess')),
          duration: const Duration(seconds: 1),
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.message;
        _saving = false;
      });
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = _i18n.t('requests.genericError');
        _saving = false;
      });
      debugPrint('Save draft failed: $e');
    }
  }

  Future<void> _submit() async {
    setState(() => _branchError = null);
    if (!_formKey.currentState!.validate()) return;
    if (_branchId == null || _branchId!.isEmpty) {
      setState(() => _branchError = _i18n.t('requests.form.branchRequired'));
      return;
    }
    if (_lines.isEmpty) return;

    _formKey.currentState!.save();
    final body = _requestBody();

    setState(() {
      _submitting = true;
      _errorMessage = null;
    });

    try {
      _offlineSubmitIdempotencyKey ??= const Uuid().v4();
      final key = _offlineSubmitIdempotencyKey!;
      final existing =
          _savedRequest ??
          await _apiClient.createRequest(body, idempotencyKey: key);
      final submitted = await _apiClient.submitRequest(existing.id);
      if (!mounted) return;
      setState(() => _submitting = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_i18n.t('requests.submitSuccess')),
          duration: const Duration(seconds: 1),
        ),
      );
      await Navigator.of(context)
          .pushReplacementNamed('/requests/detail', arguments: submitted);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.message;
        _submitting = false;
      });
    } on Exception catch (e) {
      final queued = await _queueRequestSubmission(
        body,
        idempotencyKey: _offlineSubmitIdempotencyKey,
      );
      if (!mounted) return;
      if (queued) {
        setState(() {
          _submitting = false;
          _submissionQueued = true;
        });
        return;
      }
      setState(() {
        _errorMessage = _i18n.t('requests.genericError');
        _submitting = false;
      });
      debugPrint('Submit failed: $e');
    }
  }

  PurchaseRequestCreate _requestBody() {
    return PurchaseRequestCreate(
      branchId: _branchId!,
      costCentreId: _costCentreId,
      requiredByDate: _requiredByDateController.text,
      lines: _lines
          .map(
            (l) => PurchaseRequestLineInput(
              workspaceProductId: l.workspaceProductId,
              quantity: l.quantity,
              note: l.note,
            ),
          )
          .toList(),
    );
  }

  Future<bool> _queueRequestSubmission(
    PurchaseRequestCreate body, {
    required String? idempotencyKey,
  }) async {
    final queue = _offlineQueue;
    if (queue == null) return false;
    final existingDraft = _savedRequest;
    if (existingDraft != null) {
      // The draft already exists server-side (an earlier, online "Save
      // Draft") — only the submit call itself needs replaying, not a second
      // create.
      await queue.createAndEnqueue(
        endpoint: 'requests/submit',
        payload: {'request_id': existingDraft.id},
        idempotencyKey: idempotencyKey,
      );
      return true;
    }
    await queue.createAndEnqueue(
      endpoint: 'requests',
      payload: body.toJson(),
      idempotencyKey: idempotencyKey,
    );
    return true;
  }

  static final RegExp _isoDatePattern = RegExp(r'^\d{4}-\d{2}-\d{2}$');

  String? _requiredByDateValidator(String? value) {
    if (value == null || value.isEmpty) {
      return _i18n.t('requests.form.requiredByDateRequired');
    }
    if (!_isoDatePattern.hasMatch(value)) {
      return _i18n.t('requests.form.requiredByDateInvalid');
    }
    return null;
  }

  Future<void> _pickRequiredByDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: now,
      firstDate: now,
      lastDate: now.add(const Duration(days: 365)),
    );
    if (picked == null) return;
    setState(() {
      _requiredByDateController.text =
          '${picked.year.toString().padLeft(4, '0')}-'
          '${picked.month.toString().padLeft(2, '0')}-'
          '${picked.day.toString().padLeft(2, '0')}';
    });
  }

  String? _quantityValidator(String? value) {
    if (value == null || value.isEmpty) {
      return _i18n.t('requests.form.quantityRequired');
    }
    if (!RegExp(r'^\d+(\.\d{1,6})?$').hasMatch(value)) {
      return _i18n.t('requests.form.quantityRequired');
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final i18n = _i18n;

    if (_submissionQueued) {
      return Scaffold(
        appBar: AppBar(title: Text(i18n.t('requests.form.createTitle'))),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: SubmissionQueuedBanner(
              message: i18n.t('mobileRequests.queuedMessage'),
            ),
          ),
        ),
      );
    }

    final canSubmit = _lines.isNotEmpty;

    return Scaffold(
      appBar: AppBar(
        title: Text(
          i18n.t(
            _savedRequest == null
                ? 'requests.form.createTitle'
                : 'requests.form.editTitle',
          ),
        ),
      ),
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
                    color: Theme.of(context).colorScheme.errorContainer,
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Text(_errorMessage!),
                    ),
                  ),
                InputDecorator(
                  key: const Key('requestFormBranchField'),
                  decoration: InputDecoration(
                    labelText: i18n.t('requests.form.branchLabel'),
                    errorText: _branchError,
                  ),
                  child: DropdownButtonHideUnderline(
                    child: DropdownButton<String>(
                      value: _branchId,
                      isDense: true,
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
                InputDecorator(
                  key: const Key('requestFormCostCentreField'),
                  decoration: InputDecoration(
                    labelText: i18n.t('requests.form.costCentreLabel'),
                  ),
                  child: DropdownButtonHideUnderline(
                    child: DropdownButton<String?>(
                      value: _costCentreId,
                      isDense: true,
                      hint: Text(i18n.t('requests.form.costCentreLabel')),
                      items: [
                        const DropdownMenuItem(value: null, child: Text('—')),
                        ..._costCentres.map(
                          (c) => DropdownMenuItem(
                            value: c.id,
                            child: Text(c.name),
                          ),
                        ),
                      ],
                      onChanged: (value) {
                        setState(() => _costCentreId = value);
                      },
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                TextFormField(
                  key: const Key('requestFormRequiredByField'),
                  decoration: InputDecoration(
                    labelText: i18n.t('requests.form.requiredByDateLabel'),
                    hintText: 'YYYY-MM-DD',
                    suffixIcon: IconButton(
                      key: const Key('requestFormRequiredByPickerButton'),
                      icon: const Icon(Icons.calendar_today),
                      tooltip: i18n.t('requests.form.requiredByDateLabel'),
                      onPressed: _pickRequiredByDate,
                    ),
                  ),
                  keyboardType: TextInputType.datetime,
                  validator: _requiredByDateValidator,
                  onSaved: (value) {
                    // Required-by date is saved here; the value is stored
                    // implicitly by the text field and read in _saveDraft.
                  },
                  controller: _requiredByDateController,
                ),
                const SizedBox(height: 24),
                Text(
                  i18n.t('requests.form.linesTitle'),
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                if (_lines.isEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Text(i18n.t('requests.form.atLeastOneLineRequired')),
                  ),
                ..._lines.asMap().entries.map((entry) {
                  final index = entry.key;
                  final line = entry.value;
                  return _LineItemEditor(
                    key: Key('requestLine_$index'),
                    index: index,
                    line: line,
                    i18n: i18n,
                    catalogueResults: _catalogueResults,
                    catalogueLoading: _catalogueLoading,
                    onSearch: _onCatalogueSearch,
                    onRemove: _removeLine,
                    quantityValidator: _quantityValidator,
                  );
                }),
                const SizedBox(height: 8),
                ElevatedButton.icon(
                  key: const Key('requestFormAddLineButton'),
                  onPressed: _addLine,
                  icon: const Icon(Icons.add),
                  label: Text(i18n.t('requests.form.addLineButton')),
                ),
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        key: const Key('requestFormCancelButton'),
                        onPressed: () => Navigator.of(context).pop(),
                        child: Text(i18n.t('requests.form.cancelButton')),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: ElevatedButton(
                        key: const Key('requestFormSaveDraftButton'),
                        onPressed: _saving ? null : _saveDraft,
                        child: Text(
                          _saving
                              ? i18n.t('common.loading')
                              : i18n.t('requests.form.saveDraftButton'),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    key: const Key('requestFormSubmitButton'),
                    onPressed: canSubmit && !_submitting ? _submit : null,
                    child: Text(
                      _submitting
                          ? i18n.t('requests.form.submittingButton')
                          : i18n.t('requests.form.submitButton'),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  final _requiredByDateController = TextEditingController();

  @override
  void dispose() {
    _requiredByDateController.dispose();
    _searchDebounce?.cancel();
    super.dispose();
  }
}

class _LineItemEditor extends StatefulWidget {
  const _LineItemEditor({
    super.key,
    required this.index,
    required this.line,
    required this.i18n,
    required this.catalogueResults,
    required this.catalogueLoading,
    required this.onSearch,
    required this.onRemove,
    required this.quantityValidator,
  });

  final int index;
  final _LineInput line;
  final I18nLoader i18n;
  final List<CatalogueProduct> catalogueResults;
  final bool catalogueLoading;
  final void Function(String query, int lineIndex) onSearch;
  final void Function(int index) onRemove;
  final String? Function(String?) quantityValidator;

  @override
  State<_LineItemEditor> createState() => _LineItemEditorState();
}

class _LineItemEditorState extends State<_LineItemEditor> {
  late final TextEditingController _searchController;
  late final TextEditingController _quantityController;
  late final TextEditingController _noteController;

  @override
  void initState() {
    super.initState();
    _searchController = TextEditingController();
    _quantityController = TextEditingController();
    _noteController = TextEditingController();
  }

  @override
  void dispose() {
    _searchController.dispose();
    _quantityController.dispose();
    _noteController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final i18n = widget.i18n;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextFormField(
              key: Key('requestLine_${widget.index}_productSearch'),
              controller: _searchController,
              decoration: InputDecoration(
                labelText: i18n.t('requests.form.productLabel'),
                hintText: i18n.t('mobileRequests.productSearchHint'),
              ),
              onChanged: (value) {
                widget.line.workspaceProductId = value;
                widget.onSearch(value, widget.index);
              },
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return i18n.t('requests.form.productRequired');
                }
                return null;
              },
            ),
            if (widget.catalogueLoading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (widget.catalogueResults.isNotEmpty)
              SizedBox(
                height: 120,
                child: ListView.builder(
                  key: Key('requestLine_${widget.index}_productResults'),
                  itemCount: widget.catalogueResults.length,
                  itemBuilder: (context, resultIndex) {
                    final product = widget.catalogueResults[resultIndex];
                    return ListTile(
                      key: Key(
                        'requestLine_${widget.index}_productResult_$resultIndex',
                      ),
                      title: Text(product.tenantName),
                      subtitle: Text(product.baseUnit),
                      onTap: () {
                        setState(() {
                          widget.line.workspaceProductId = product.id;
                          _searchController.text = product.tenantName;
                        });
                        widget.onSearch('', widget.index);
                      },
                    );
                  },
                ),
              ),
            const SizedBox(height: 8),
            TextFormField(
              key: Key('requestLine_${widget.index}_quantity'),
              controller: _quantityController,
              decoration: InputDecoration(
                labelText: i18n.t('requests.form.quantityLabel'),
              ),
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              validator: widget.quantityValidator,
              onSaved: (value) => widget.line.quantity = value ?? '',
            ),
            const SizedBox(height: 8),
            TextFormField(
              key: Key('requestLine_${widget.index}_note'),
              controller: _noteController,
              decoration: InputDecoration(
                labelText: i18n.t('requests.form.noteLabel'),
              ),
              onSaved: (value) => widget.line.note = value,
            ),
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: TextButton.icon(
                key: Key('requestLine_${widget.index}_removeButton'),
                onPressed: () => widget.onRemove(widget.index),
                icon: const Icon(Icons.delete_outline),
                label: Text(i18n.t('requests.form.removeLineButton')),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
