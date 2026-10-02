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

    test('recovers a photo lost to activity destruction', () async {
      final camera = ImagePickerCameraCapture(
        retrieveLostData: () async =>
            LostDataResponse(file: XFile('/tmp/recovered.jpg')),
      );

      final recovered = await camera.recoverLostCapture();
      expect(recovered?.filePath, '/tmp/recovered.jpg');
    });

    test('returns null when there is nothing to recover', () async {
      final camera = ImagePickerCameraCapture(
        retrieveLostData: () async => LostDataResponse.empty(),
      );

      expect(await camera.recoverLostCapture(), isNull);
    });

    test('returns null when recovery throws', () async {
      final camera = ImagePickerCameraCapture(
        retrieveLostData: () async => throw Exception('platform error'),
      );

      expect(await camera.recoverLostCapture(), isNull);
    });
  });
}
