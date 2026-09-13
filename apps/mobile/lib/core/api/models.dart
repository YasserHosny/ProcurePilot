import 'package:flutter/foundation.dart';

/// Platform values supported by the mobile device registration endpoint.
enum DevicePlatform {
  ios,
  android,
}

/// {@template device_registration}
/// A registered push-token row for the signed-in member/device.
/// {@endtemplate}
@immutable
class DeviceRegistration {
  const DeviceRegistration({
    required this.id,
    required this.memberId,
    required this.platform,
    required this.pushToken,
    required this.lastSeenAt,
  });

  final String id;
  final String memberId;
  final DevicePlatform platform;
  final String pushToken;
  final DateTime lastSeenAt;

  factory DeviceRegistration.fromJson(Map<String, dynamic> json) {
    return DeviceRegistration(
      id: json['id'] as String,
      memberId: json['member_id'] as String,
      platform: _parsePlatform(json['platform'] as String),
      pushToken: json['push_token'] as String,
      lastSeenAt: DateTime.parse(json['last_seen_at'] as String),
    );
  }

  static DevicePlatform _parsePlatform(String value) {
    return DevicePlatform.values.firstWhere(
      (p) => p.name == value,
      orElse: () => throw FormatException('Unknown device platform: $value'),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'member_id': memberId,
        'platform': platform.name,
        'push_token': pushToken,
        'last_seen_at': lastSeenAt.toIso8601String(),
      };
}

/// {@template device_registration_create}
/// Payload for [POST /devices].
/// {@endtemplate}
@immutable
class DeviceRegistrationCreate {
  const DeviceRegistrationCreate({
    required this.platform,
    required this.pushToken,
  });

  final DevicePlatform platform;
  final String pushToken;

  Map<String, dynamic> toJson() => {
        'platform': platform.name,
        'push_token': pushToken,
      };
}

/// {@template low_stock_report}
/// A one-tap low-stock signal raised from the mobile app.
/// {@endtemplate}
@immutable
class LowStockReport {
  const LowStockReport({
    required this.id,
    required this.branchId,
    required this.memberId,
    required this.workspaceProductId,
    this.countRemaining,
    required this.createdAt,
  });

  final String id;
  final String branchId;
  final String memberId;
  final String workspaceProductId;

  /// Decimal-shaped value is represented as a string, never a Dart double.
  final String? countRemaining;

  final DateTime createdAt;

  factory LowStockReport.fromJson(Map<String, dynamic> json) {
    return LowStockReport(
      id: json['id'] as String,
      branchId: json['branch_id'] as String,
      memberId: json['member_id'] as String,
      workspaceProductId: json['workspace_product_id'] as String,
      countRemaining: json['count_remaining'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'branch_id': branchId,
        'member_id': memberId,
        'workspace_product_id': workspaceProductId,
        if (countRemaining != null) 'count_remaining': countRemaining,
        'created_at': createdAt.toIso8601String(),
      };
}

/// {@template low_stock_report_create}
/// Payload for [POST /low-stock-reports].
/// {@endtemplate}
@immutable
class LowStockReportCreate {
  const LowStockReportCreate({
    required this.branchId,
    required this.workspaceProductId,
    this.countRemaining,
  });

  final String branchId;
  final String workspaceProductId;
  final String? countRemaining;

  Map<String, dynamic> toJson() => {
        'branch_id': branchId,
        'workspace_product_id': workspaceProductId,
        if (countRemaining != null) 'count_remaining': countRemaining,
      };
}

/// {@template low_stock_report_list}
/// Cursor-paginated list of low-stock reports visible to the caller.
/// {@endtemplate}
@immutable
class LowStockReportList {
  const LowStockReportList({
    required this.items,
    required this.nextCursor,
  });

  final List<LowStockReport> items;
  final String? nextCursor;

  factory LowStockReportList.fromJson(Map<String, dynamic> json) {
    final items = (json['items'] as List<dynamic>)
        .map((e) => LowStockReport.fromJson(e as Map<String, dynamic>))
        .toList();
    return LowStockReportList(
      items: items,
      nextCursor: json['next_cursor'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'items': items.map((e) => e.toJson()).toList(),
        'next_cursor': nextCursor,
      };
}

/// Money is never a bare number — Constitution Principle VII.
@immutable
class Money {
  const Money({required this.amount, required this.currency});

  final String amount;
  final String currency;

  factory Money.fromJson(Map<String, dynamic> json) {
    return Money(
      amount: json['amount'] as String,
      currency: json['currency'] as String,
    );
  }

  Map<String, dynamic> toJson() => {'amount': amount, 'currency': currency};
}

/// A single line on a purchase request.
@immutable
class PurchaseRequestLine {
  const PurchaseRequestLine({
    required this.id,
    required this.workspaceProductId,
    required this.quantity,
    this.note,
    this.estimatedUnitPrice,
    this.quantityReceived,
  });

  final String id;
  final String workspaceProductId;
  final String quantity;
  final String? note;
  final Money? estimatedUnitPrice;

  /// Set once the parent request is `delivered` (chunk R2.3) — null until then. A decimal
  /// string, same convention as [quantity].
  final String? quantityReceived;

  factory PurchaseRequestLine.fromJson(Map<String, dynamic> json) {
    return PurchaseRequestLine(
      id: json['id'] as String,
      workspaceProductId: json['workspace_product_id'] as String,
      quantity: json['quantity'] as String,
      note: json['note'] as String?,
      estimatedUnitPrice: json['estimated_unit_price'] == null
          ? null
          : Money.fromJson(json['estimated_unit_price'] as Map<String, dynamic>),
      quantityReceived: json['quantity_received'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'workspace_product_id': workspaceProductId,
        'quantity': quantity,
        if (note != null) 'note': note,
        if (estimatedUnitPrice != null)
          'estimated_unit_price': estimatedUnitPrice!.toJson(),
      };
}

/// Input shape for a purchase-request line (create/update).
@immutable
class PurchaseRequestLineInput {
  const PurchaseRequestLineInput({
    required this.workspaceProductId,
    required this.quantity,
    this.note,
  });

  final String workspaceProductId;
  final String quantity;
  final String? note;

  Map<String, dynamic> toJson() => {
        'workspace_product_id': workspaceProductId,
        'quantity': quantity,
        if (note != null) 'note': note,
      };
}

/// Routing/approval step attached to a submitted purchase request.
@immutable
class ApprovalStep {
  const ApprovalStep({
    required this.id,
    required this.assignedMembershipId,
    required this.source,
    required this.status,
    this.comment,
    this.decidedByMembershipId,
    this.decidedAt,
  });

  final String id;
  final String assignedMembershipId;
  final String source;
  final String status;
  final String? comment;
  final String? decidedByMembershipId;
  final DateTime? decidedAt;

  factory ApprovalStep.fromJson(Map<String, dynamic> json) {
    return ApprovalStep(
      id: json['id'] as String,
      assignedMembershipId: json['assigned_membership_id'] as String,
      source: json['source'] as String,
      status: json['status'] as String,
      comment: json['comment'] as String?,
      decidedByMembershipId: json['decided_by_membership_id'] as String?,
      decidedAt: json['decided_at'] == null
          ? null
          : DateTime.parse(json['decided_at'] as String),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'assigned_membership_id': assignedMembershipId,
        'source': source,
        'status': status,
        if (comment != null) 'comment': comment,
        if (decidedByMembershipId != null)
          'decided_by_membership_id': decidedByMembershipId,
        if (decidedAt != null) 'decided_at': decidedAt!.toIso8601String(),
      };
}

/// Budget status for a purchase request.
@immutable
class BudgetStatus {
  const BudgetStatus({required this.remainingAmount, required this.exceeds});

  final Money remainingAmount;
  final bool exceeds;

  factory BudgetStatus.fromJson(Map<String, dynamic> json) {
    return BudgetStatus(
      remainingAmount: Money.fromJson(
        json['remaining_amount'] as Map<String, dynamic>,
      ),
      exceeds: json['exceeds'] as bool,
    );
  }

  Map<String, dynamic> toJson() => {
        'remaining_amount': remainingAmount.toJson(),
        'exceeds': exceeds,
      };
}

/// A purchase request, as returned by the 008 Requests + Approvals contract.
@immutable
class PurchaseRequest {
  const PurchaseRequest({
    required this.id,
    required this.branchId,
    this.costCentreId,
    required this.requestedByMembershipId,
    required this.requiredByDate,
    required this.status,
    required this.lines,
    this.estimatedTotal,
    required this.hasIncompleteEstimate,
    this.budgetStatus,
    this.approvalStep,
    this.submittedAt,
    this.withdrawnAt,
    required this.createdAt,
    this.updatedAt,
    this.deliveredAt,
    this.deliveryConfirmedByMembershipId,
    this.hasDeliveryDiscrepancy = false,
  });

  final String id;
  final String branchId;
  final String? costCentreId;
  final String requestedByMembershipId;
  final String requiredByDate;
  final String status;
  final List<PurchaseRequestLine> lines;
  final Money? estimatedTotal;
  final bool hasIncompleteEstimate;
  final BudgetStatus? budgetStatus;
  final ApprovalStep? approvalStep;
  final DateTime? submittedAt;
  final DateTime? withdrawnAt;
  final DateTime createdAt;
  final DateTime? updatedAt;

  /// Delivery-lifecycle fields (chunk R2.3) — null/false until the request reaches
  /// `ordered`/`delivered`. `status` itself already carries those two new values; these three
  /// fields are the facts recorded alongside the `delivered` transition specifically.
  final DateTime? deliveredAt;
  final String? deliveryConfirmedByMembershipId;
  final bool hasDeliveryDiscrepancy;

  factory PurchaseRequest.fromJson(Map<String, dynamic> json) {
    final lines = (json['lines'] as List<dynamic>)
        .map((e) => PurchaseRequestLine.fromJson(e as Map<String, dynamic>))
        .toList();
    return PurchaseRequest(
      id: json['id'] as String,
      branchId: json['branch_id'] as String,
      costCentreId: json['cost_centre_id'] as String?,
      requestedByMembershipId: json['requested_by_membership_id'] as String,
      requiredByDate: json['required_by_date'] as String,
      status: json['status'] as String,
      lines: lines,
      estimatedTotal: json['estimated_total'] == null
          ? null
          : Money.fromJson(json['estimated_total'] as Map<String, dynamic>),
      hasIncompleteEstimate: json['has_incomplete_estimate'] as bool,
      budgetStatus: json['budget_status'] == null
          ? null
          : BudgetStatus.fromJson(json['budget_status'] as Map<String, dynamic>),
      approvalStep: json['approval_step'] == null
          ? null
          : ApprovalStep.fromJson(json['approval_step'] as Map<String, dynamic>),
      submittedAt: json['submitted_at'] == null
          ? null
          : DateTime.parse(json['submitted_at'] as String),
      withdrawnAt: json['withdrawn_at'] == null
          ? null
          : DateTime.parse(json['withdrawn_at'] as String),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: json['updated_at'] == null
          ? null
          : DateTime.parse(json['updated_at'] as String),
      deliveredAt: json['delivered_at'] == null
          ? null
          : DateTime.parse(json['delivered_at'] as String),
      deliveryConfirmedByMembershipId:
          json['delivery_confirmed_by_membership_id'] as String?,
      hasDeliveryDiscrepancy:
          json['has_delivery_discrepancy'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'branch_id': branchId,
        if (costCentreId != null) 'cost_centre_id': costCentreId,
        'requested_by_membership_id': requestedByMembershipId,
        'required_by_date': requiredByDate,
        'status': status,
        'lines': lines.map((e) => e.toJson()).toList(),
        if (estimatedTotal != null) 'estimated_total': estimatedTotal!.toJson(),
        'has_incomplete_estimate': hasIncompleteEstimate,
        if (budgetStatus != null) 'budget_status': budgetStatus!.toJson(),
        if (approvalStep != null) 'approval_step': approvalStep!.toJson(),
        if (submittedAt != null) 'submitted_at': submittedAt!.toIso8601String(),
        if (withdrawnAt != null) 'withdrawn_at': withdrawnAt!.toIso8601String(),
        'created_at': createdAt.toIso8601String(),
        if (updatedAt != null) 'updated_at': updatedAt!.toIso8601String(),
        if (deliveredAt != null) 'delivered_at': deliveredAt!.toIso8601String(),
        if (deliveryConfirmedByMembershipId != null)
          'delivery_confirmed_by_membership_id': deliveryConfirmedByMembershipId,
        'has_delivery_discrepancy': hasDeliveryDiscrepancy,
      };
}

/// Payload for [POST /requests].
@immutable
class PurchaseRequestCreate {
  const PurchaseRequestCreate({
    required this.branchId,
    this.costCentreId,
    required this.requiredByDate,
    required this.lines,
  });

  final String branchId;
  final String? costCentreId;
  final String requiredByDate;
  final List<PurchaseRequestLineInput> lines;

  Map<String, dynamic> toJson() => {
        'branch_id': branchId,
        if (costCentreId != null) 'cost_centre_id': costCentreId,
        'required_by_date': requiredByDate,
        'lines': lines.map((e) => e.toJson()).toList(),
      };
}

/// Payload for [PATCH /requests/{request_id}].
@immutable
class PurchaseRequestUpdate {
  const PurchaseRequestUpdate({
    this.branchId,
    this.costCentreId,
    this.requiredByDate,
    this.lines,
  });

  final String? branchId;
  final String? costCentreId;
  final String? requiredByDate;
  final List<PurchaseRequestLineInput>? lines;

  Map<String, dynamic> toJson() => {
        if (branchId != null) 'branch_id': branchId,
        if (costCentreId != null) 'cost_centre_id': costCentreId,
        if (requiredByDate != null) 'required_by_date': requiredByDate,
        if (lines != null)
          'lines': lines!.map((e) => e.toJson()).toList(),
      };
}

/// Cursor-paginated list of purchase requests.
@immutable
class PurchaseRequestList {
  const PurchaseRequestList({required this.items, this.nextCursor});

  final List<PurchaseRequest> items;
  final String? nextCursor;

  factory PurchaseRequestList.fromJson(Map<String, dynamic> json) {
    final items = (json['items'] as List<dynamic>)
        .map((e) => PurchaseRequest.fromJson(e as Map<String, dynamic>))
        .toList();
    return PurchaseRequestList(
      items: items,
      nextCursor: json['next_cursor'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'items': items.map((e) => e.toJson()).toList(),
        'next_cursor': nextCursor,
      };
}

/// Organisation branch.
@immutable
class Branch {
  const Branch({
    required this.id,
    required this.name,
    this.address,
    this.region,
    required this.isActive,
    required this.createdAt,
  });

  final String id;
  final String name;
  final String? address;
  final String? region;
  final bool isActive;
  final DateTime createdAt;

  factory Branch.fromJson(Map<String, dynamic> json) {
    return Branch(
      id: json['id'] as String,
      name: json['name'] as String,
      address: json['address'] as String?,
      region: json['region'] as String?,
      isActive: json['is_active'] as bool,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        if (address != null) 'address': address,
        if (region != null) 'region': region,
        'is_active': isActive,
        'created_at': createdAt.toIso8601String(),
      };
}

/// Cursor-paginated list of branches.
@immutable
class BranchList {
  const BranchList({required this.items, this.nextCursor});

  final List<Branch> items;
  final String? nextCursor;

  factory BranchList.fromJson(Map<String, dynamic> json) {
    final items = (json['items'] as List<dynamic>)
        .map((e) => Branch.fromJson(e as Map<String, dynamic>))
        .toList();
    return BranchList(
      items: items,
      nextCursor: json['next_cursor'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'items': items.map((e) => e.toJson()).toList(),
        'next_cursor': nextCursor,
      };
}

/// Organisation cost centre.
@immutable
class CostCentre {
  const CostCentre({
    required this.id,
    required this.name,
    required this.code,
    this.budgetOwnerMembershipId,
    this.branchId,
    required this.isArchived,
    required this.createdAt,
  });

  final String id;
  final String name;
  final String code;
  final String? budgetOwnerMembershipId;
  final String? branchId;
  final bool isArchived;
  final DateTime createdAt;

  factory CostCentre.fromJson(Map<String, dynamic> json) {
    return CostCentre(
      id: json['id'] as String,
      name: json['name'] as String,
      code: json['code'] as String,
      budgetOwnerMembershipId: json['budget_owner_membership_id'] as String?,
      branchId: json['branch_id'] as String?,
      isArchived: json['is_archived'] as bool,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'code': code,
        if (budgetOwnerMembershipId != null)
          'budget_owner_membership_id': budgetOwnerMembershipId,
        if (branchId != null) 'branch_id': branchId,
        'is_archived': isArchived,
        'created_at': createdAt.toIso8601String(),
      };
}

/// Cursor-paginated list of cost centres.
@immutable
class CostCentreList {
  const CostCentreList({required this.items, this.nextCursor});

  final List<CostCentre> items;
  final String? nextCursor;

  factory CostCentreList.fromJson(Map<String, dynamic> json) {
    final items = (json['items'] as List<dynamic>)
        .map((e) => CostCentre.fromJson(e as Map<String, dynamic>))
        .toList();
    return CostCentreList(
      items: items,
      nextCursor: json['next_cursor'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'items': items.map((e) => e.toJson()).toList(),
        'next_cursor': nextCursor,
      };
}

/// Catalogue product returned by [GET /products].
@immutable
class CatalogueProduct {
  const CatalogueProduct({
    required this.id,
    required this.tenantName,
    this.brand,
    required this.canonicalName,
    this.variant,
    this.gtin,
    required this.baseUnit,
    required this.status,
    required this.createdAt,
  });

  final String id;
  final String tenantName;
  final String? brand;
  final String canonicalName;
  final String? variant;
  final String? gtin;
  final String baseUnit;
  final String status;
  final DateTime createdAt;

  factory CatalogueProduct.fromJson(Map<String, dynamic> json) {
    return CatalogueProduct(
      id: json['id'] as String,
      tenantName: json['tenant_name'] as String,
      brand: json['brand'] as String?,
      canonicalName: json['canonical_name'] as String,
      variant: json['variant'] as String?,
      gtin: json['gtin'] as String?,
      baseUnit: json['base_unit'] as String,
      status: json['status'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'tenant_name': tenantName,
        if (brand != null) 'brand': brand,
        'canonical_name': canonicalName,
        if (variant != null) 'variant': variant,
        if (gtin != null) 'gtin': gtin,
        'base_unit': baseUnit,
        'status': status,
        'created_at': createdAt.toIso8601String(),
      };
}

/// Cursor-paginated list of catalogue products.
@immutable
class CatalogueProductList {
  const CatalogueProductList({required this.items, this.nextCursor});

  final List<CatalogueProduct> items;
  final String? nextCursor;

  factory CatalogueProductList.fromJson(Map<String, dynamic> json) {
    final items = (json['items'] as List<dynamic>)
        .map((e) => CatalogueProduct.fromJson(e as Map<String, dynamic>))
        .toList();
    return CatalogueProductList(
      items: items,
      nextCursor: json['next_cursor'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'items': items.map((e) => e.toJson()).toList(),
        'next_cursor': nextCursor,
      };
}

/// Generic API exception carrying the contract's error envelope shape.
class ApiException implements Exception {
  const ApiException({
    required this.statusCode,
    required this.code,
    required this.message,
    this.details,
    required this.traceId,
  });

  final int statusCode;
  final String code;
  final String message;
  final Map<String, dynamic>? details;
  final String traceId;

  @override
  String toString() => 'ApiException[$statusCode] $code: $message (trace: $traceId)';
}
