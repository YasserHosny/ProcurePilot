import 'package:flutter/foundation.dart';

import '../../core/api/mobile_api_client.dart';
import '../../core/api/models.dart';
import 'notification_permission.dart';

/// Requests notification permission and registers the resulting token.
class PushNotificationRegistration {
  PushNotificationRegistration({
    required this.permission,
    required this.mobileApiClient,
    DevicePlatform? platform,
  }) : platform = platform ?? _currentPlatform;

  final NotificationPermission permission;
  final MobileApiClient mobileApiClient;
  final DevicePlatform platform;

  Future<void> registerIfGranted() async {
    final result = await permission.requestPermission();
    final token = result.pushToken;
    if (result.status != NotificationPermissionStatus.granted ||
        token == null ||
        token.isEmpty) {
      return;
    }

    await mobileApiClient.registerDevice(platform: platform, pushToken: token);
  }

  static DevicePlatform get _currentPlatform {
    return defaultTargetPlatform == TargetPlatform.iOS
        ? DevicePlatform.ios
        : DevicePlatform.android;
  }
}
