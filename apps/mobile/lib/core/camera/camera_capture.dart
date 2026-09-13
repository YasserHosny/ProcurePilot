import 'package:flutter/foundation.dart';

/// A photo captured through [CameraCapture.capturePhoto].
@immutable
class CapturedPhoto {
  const CapturedPhoto({required this.filePath});

  /// Local filesystem path to the captured image, ready to be read and
  /// uploaded by whichever screen requested the capture.
  final String filePath;
}

/// Abstraction over platform camera access so tests can inject a fake,
/// mirroring [BiometricAuth]'s exact shape
/// (`apps/mobile/lib/core/auth/biometric_gate.dart`).
///
/// A declined or unavailable camera must never block the flow that requested
/// it (spec.md FR-007, 010-mobile-approvals-receipt) — `capturePhoto()`
/// returns `null` rather than throwing when the user cancels or permission
/// is refused; the caller treats a photo as optional evidence, not a
/// requirement.
abstract class CameraCapture {
  Future<bool> isAvailable();
  Future<CapturedPhoto?> capturePhoto();
}

/// Platform-agnostic stand-in until a real camera plugin is introduced.
///
/// No concrete camera/image-picker package is wired into this codebase yet
/// (research.md R4, 010-mobile-approvals-receipt) — this stand-in lets the
/// rest of this chunk's plumbing (screens, the offline queue, upload) be
/// built and tested against a real *shape* now, with the actual platform
/// integration left to whichever task builds the quality-issue report
/// screen that needs to call a real camera.
class StandInCameraCapture implements CameraCapture {
  const StandInCameraCapture();

  @override
  Future<bool> isAvailable() async => false;

  @override
  Future<CapturedPhoto?> capturePhoto() async => null;
}
