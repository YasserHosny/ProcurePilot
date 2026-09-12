import 'package:uuid/uuid.dart';

/// Result of asking the device for notification permission.
enum NotificationPermissionStatus {
  granted,
  declined,
}

/// Permission result plus the push token needed for backend registration.
class NotificationPermissionResult {
  const NotificationPermissionResult._({
    required this.status,
    this.pushToken,
  });

  final NotificationPermissionStatus status;
  final String? pushToken;

  factory NotificationPermissionResult.granted(String pushToken) {
    return NotificationPermissionResult._(
      status: NotificationPermissionStatus.granted,
      pushToken: pushToken,
    );
  }

  static const declined = NotificationPermissionResult._(
    status: NotificationPermissionStatus.declined,
  );
}

/// Abstraction over platform notification APIs so tests can inject a fake.
abstract class NotificationPermission {
  Future<NotificationPermissionResult> requestPermission();

  /// Emits notification-tap payloads from the platform layer.
  ///
  /// Phase 6 payloads carry only `purchase_request_id`.
  Stream<Map<String, String>> get notificationTaps;
}

/// Platform-agnostic stand-in until a real FCM/APNs plugin is introduced.
///
/// The backend's provider side is intentionally stubbed in this wave, so this
/// adapter records an honest locally-generated placeholder token without adding
/// a native push dependency that cannot yet be exercised end to end.
class StandInNotificationPermission implements NotificationPermission {
  StandInNotificationPermission({Uuid? uuid}) : _uuid = uuid ?? const Uuid();

  final Uuid _uuid;

  @override
  Future<NotificationPermissionResult> requestPermission() async {
    return NotificationPermissionResult.granted('placeholder-${_uuid.v4()}');
  }

  @override
  Stream<Map<String, String>> get notificationTaps => const Stream.empty();
}
