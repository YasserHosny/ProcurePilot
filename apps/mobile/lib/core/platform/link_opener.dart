import 'package:flutter/foundation.dart';
import 'package:url_launcher/url_launcher.dart';

/// Abstraction over platform external URL launching so tests can inject a fake
/// without needing platform channels or plugins.
abstract class LinkOpener {
  Future<bool> open(Uri uri);
  Future<bool> openUrl(Uri uri) => open(uri);
  Future<bool> openString(String url) => open(Uri.parse(url));
}

/// LinkOpener implementation backed by the official `url_launcher` plugin.
class UrlLauncherLinkOpener implements LinkOpener {
  const UrlLauncherLinkOpener();

  @override
  Future<bool> open(Uri uri) async {
    try {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    } on Object catch (error, stackTrace) {
      debugPrint('Failed to open link $uri: $error\n$stackTrace');
      return false;
    }
  }

  @override
  Future<bool> openUrl(Uri uri) => open(uri);

  @override
  Future<bool> openString(String url) => open(Uri.parse(url));
}
