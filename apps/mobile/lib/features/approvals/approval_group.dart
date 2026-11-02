import 'package:intl/intl.dart';

import '../../core/api/models.dart';
import '../../core/format/money_format.dart';
import '../../core/format/quantity_format.dart';
import '../../core/i18n/i18n_loader.dart';

/// Route arguments retaining every loaded request behind one queue entry.
class ApprovalGroup {
  const ApprovalGroup({required this.summary, required this.requests});

  final RequestGroupSummary summary;
  final List<PurchaseRequest> requests;
}

String approvalGroupSummary(I18nLoader i18n, RequestGroupSummary group) {
  // The shared catalogue uses CLDR plural categories; I18nLoader resolves
  // dotted keys and interpolation, so select the category before looking up.
  final category = Intl.pluralLogic(
    group.size,
    locale: i18n.locale,
    zero: 'zero',
    one: 'one',
    two: 'two',
    few: 'few',
    many: 'many',
    other: 'other',
  );
  final count = i18n.t(
    'approvals.requestCount.$category',
    params: {
      'count': formatDecimal(group.size.toString(), locale: i18n.locale),
    },
  );
  final saving = group.saving;
  return i18n.t(
    saving == null
        ? 'approvals.splitGroup.summaryNoSaving'
        : 'approvals.splitGroup.summary',
    params: {
      'short': group.rfqId.length > 8
          ? group.rfqId.substring(0, 8)
          : group.rfqId,
      'requests': count,
      'total': formatMoney(
        group.combinedTotal.amount,
        group.combinedTotal.currency,
        locale: i18n.locale,
      ),
      if (saving != null)
        'saving': formatMoney(
          saving.amount,
          saving.currency,
          locale: i18n.locale,
        ),
    },
  );
}
