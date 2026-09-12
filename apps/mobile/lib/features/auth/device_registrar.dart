import '../../core/api/mobile_api_client.dart';
import '../../core/auth/auth_service.dart';

/// Bridges [AuthService.signOut] to the R2.2 mobile API's device-deletion
/// endpoint.
///
/// [AuthService] already owns the decision of whether to call
/// [DELETE /devices/{id}] and the best-effort error handling; this registrar
/// simply adapts the typed API client to the [DeviceRegistrar] interface.
class MobileDeviceRegistrar implements DeviceRegistrar {
  const MobileDeviceRegistrar(this._client);

  final MobileApiClient _client;

  @override
  Future<void> deleteDevice(String deviceId) => _client.deleteDevice(deviceId);
}
