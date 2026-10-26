import 'package:flutter/foundation.dart';
import 'package:package_info_plus/package_info_plus.dart';

/// Abstraction over platform app version querying so tests can inject a fake
/// without needing platform channels or plugins.
abstract class AppVersionProvider {
  Future<String> getVersionString();
  Future<String> getVersion() => getVersionString();
}

typedef VersionProvider = AppVersionProvider;

/// AppVersionProvider implementation backed by the official `package_info_plus` plugin.
class PackageInfoVersionProvider implements AppVersionProvider {
  const PackageInfoVersionProvider();

  @override
  Future<String> getVersionString() async {
    try {
      final info = await PackageInfo.fromPlatform();
      final version = info.version;
      final build = info.buildNumber;
      if (build.isNotEmpty) {
        return '$version ($build)';
      }
      return version;
    } on Object catch (error, stackTrace) {
      debugPrint('Failed to get package info: $error\n$stackTrace');
      return '';
    }
  }

  @override
  Future<String> getVersion() => getVersionString();
}
