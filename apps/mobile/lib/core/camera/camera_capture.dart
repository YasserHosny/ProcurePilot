import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';

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

  /// Recovers a photo whose [capturePhoto] call never returned because the
  /// OS reclaimed this app's process while the external camera activity was
  /// in front (common under memory pressure on Android). Callers should
  /// invoke this once when the screen that initiated capture is restored,
  /// before assuming "no photo" means the user never took one.
  Future<CapturedPhoto?> recoverLostCapture();
}

typedef CameraPhotoPicker = Future<XFile?> Function({
  required ImageSource source,
});

typedef LostCaptureRetriever = Future<LostDataResponse> Function();

Future<XFile?> _pickWithImagePicker({required ImageSource source}) =>
    ImagePicker().pickImage(source: source);

Future<LostDataResponse> _retrieveLostDataWithImagePicker() =>
    ImagePicker().retrieveLostData();

/// CameraCapture adapter backed by the official Flutter image picker plugin.
class ImagePickerCameraCapture implements CameraCapture {
  const ImagePickerCameraCapture({
    this.pickImage = _pickWithImagePicker,
    this.retrieveLostData = _retrieveLostDataWithImagePicker,
  });

  final CameraPhotoPicker pickImage;
  final LostCaptureRetriever retrieveLostData;

  @override
  Future<bool> isAvailable() async {
    // A camera is expected on supported mobile devices; image_picker reports
    // absent hardware or denied access as a null/failed capture. Keeping this
    // true lets the optional capture action be attempted without gating flow.
    return true;
  }

  @override
  Future<CapturedPhoto?> capturePhoto() async {
    try {
      final image = await pickImage(source: ImageSource.camera);
      return image == null ? null : CapturedPhoto(filePath: image.path);
    } on Object catch (error, stackTrace) {
      debugPrint('Camera capture was unavailable: $error\n$stackTrace');
      return null;
    }
  }

  @override
  Future<CapturedPhoto?> recoverLostCapture() async {
    try {
      final response = await retrieveLostData();
      if (response.isEmpty || response.file == null) return null;
      return CapturedPhoto(filePath: response.file!.path);
    } on Object catch (error, stackTrace) {
      debugPrint('Lost-capture recovery failed: $error\n$stackTrace');
      return null;
    }
  }
}

/// Null-object implementation retained for callers that explicitly need to
/// disable camera capture (for example, platform-independent setup).
class StandInCameraCapture implements CameraCapture {
  const StandInCameraCapture();

  @override
  Future<bool> isAvailable() async => false;

  @override
  Future<CapturedPhoto?> capturePhoto() async => null;

  @override
  Future<CapturedPhoto?> recoverLostCapture() async => null;
}
