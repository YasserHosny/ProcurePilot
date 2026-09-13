import 'package:flutter/material.dart';

import '../../core/api/models.dart';
import '../../core/api/requests_api_client.dart';
import '../../core/i18n/i18n_loader.dart';
import '../requests/request_detail_screen.dart';
import '../service_provider.dart';

class DeliveryConfirmationScreen extends StatefulWidget {
  const DeliveryConfirmationScreen({super.key});

  @override
  State<DeliveryConfirmationScreen> createState() =>
      _DeliveryConfirmationScreenState();
}

class _DeliveryConfirmationScreenState
    extends State<DeliveryConfirmationScreen> {
  final _controllers = <String, TextEditingController>{};
  PurchaseRequest? _request;
  bool _submitting = false;
  String? _message;
  bool _messageIsError = false;

  RequestsApiClient get _apiClient =>
      ServiceProvider.of(context).requestsApiClient;
  I18nLoader get _i18n => ServiceProvider.of(context).i18n;

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  void _ensureControllers(PurchaseRequest request) {
    for (final line in request.lines) {
      _controllers.putIfAbsent(
        line.id,
        () =>
            TextEditingController(text: line.quantityReceived ?? line.quantity),
      );
    }
  }

  Future<void> _submit(PurchaseRequest request) async {
    setState(() {
      _submitting = true;
      _message = null;
      _messageIsError = false;
    });

    try {
      final confirmed = await _apiClient.confirmDelivery(
        request.id,
        request.lines
            .map(
              (line) => DeliveryLineInput(
                purchaseRequestLineId: line.id,
                quantityReceived: _controllers[line.id]!.text.trim(),
              ),
            )
            .toList(),
      );
      if (!mounted) return;
      setState(() {
        _request = confirmed;
        _message = _i18n.t('delivery.successMessage');
        _messageIsError = false;
      });
      _ensureControllers(confirmed);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _message = _deliveryErrorMessage(e);
        _messageIsError = true;
      });
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() {
        _message = _i18n.t('delivery.genericError');
        _messageIsError = true;
      });
      debugPrint('Failed to confirm delivery: $e');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  String _deliveryErrorMessage(ApiException error) {
    if (error.statusCode == 409 && error.details?['reason'] == 'not_ordered') {
      return _i18n.t('delivery.notOrderedError');
    }
    if (error.statusCode == 422) {
      return _i18n.t('delivery.invalidLinesError');
    }
    return _i18n.t('delivery.genericError');
  }

  @override
  Widget build(BuildContext context) {
    final args = ModalRoute.of(context)?.settings.arguments;
    final i18n = _i18n;
    final initialRequest = _request ?? (args is PurchaseRequest ? args : null);

    if (initialRequest == null) {
      return Scaffold(
        appBar: AppBar(title: Text(i18n.t('delivery.title'))),
        body: Center(child: Text(i18n.t('delivery.notAvailable'))),
      );
    }

    _request = initialRequest;
    _ensureControllers(initialRequest);

    return Scaffold(
      appBar: AppBar(title: Text(i18n.t('delivery.title'))),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            RequestContextSection(request: initialRequest),
            const SizedBox(height: 16),
            Text(
              i18n.t('delivery.linesTitle'),
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            ...initialRequest.lines.asMap().entries.map((entry) {
              final line = entry.value;
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: TextField(
                  key: Key('deliveryQuantityField_${entry.key}'),
                  controller: _controllers[line.id],
                  enabled: !_submitting,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: InputDecoration(
                    labelText: i18n.t('delivery.quantityReceivedLabel'),
                    helperText: i18n.t(
                      'delivery.orderedQuantityHelper',
                      params: {'quantity': line.quantity},
                    ),
                    border: const OutlineInputBorder(),
                  ),
                ),
              );
            }),
            if (_message != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Text(
                  _message!,
                  key: const Key('deliveryConfirmationMessage'),
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
                    key: const Key('deliveryCancelButton'),
                    onPressed: _submitting
                        ? null
                        : () => Navigator.of(context).pop(),
                    child: Text(i18n.t('delivery.cancelButton')),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    key: const Key('deliverySubmitButton'),
                    onPressed: _submitting
                        ? null
                        : () => _submit(initialRequest),
                    child: Text(
                      _submitting
                          ? i18n.t('delivery.submittingButton')
                          : i18n.t('delivery.submitButton'),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
