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
