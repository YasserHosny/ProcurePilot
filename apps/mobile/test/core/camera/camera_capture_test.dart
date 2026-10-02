import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:procurepilot_mobile/core/camera/camera_capture.dart';

void main() {
  group('ImagePickerCameraCapture', () {
    test('reports the mobile camera action as available', () async {
      expect(await ImagePickerCameraCapture().isAvailable(), isTrue);
    });

    test('returns null when the user cancels capture', () async {
      ImageSource? requestedSource;
      final camera = ImagePickerCameraCapture(
        pickImage: ({required source}) async {
          requestedSource = source;
          return null;
        },
      );

      expect(await camera.capturePhoto(), isNull);
      expect(requestedSource, ImageSource.camera);
    });

    test('returns null when the plugin throws', () async {
      final camera = ImagePickerCameraCapture(
        pickImage: ({required source}) async => throw Exception('camera denied'),
      );

      expect(await camera.capturePhoto(), isNull);
    });
  });
}
