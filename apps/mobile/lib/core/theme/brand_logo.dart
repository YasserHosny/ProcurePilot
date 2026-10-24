import 'package:flutter/material.dart';

import '../../features/service_provider.dart';

/// The Converge logo (docs/brand/README.md): the horizontal lockup, in Arabic
/// when the locale is Arabic, or the mark alone below 24 px.
///
/// It is never mirrored in RTL: the arrow means "forward", not reading direction.
class BrandLogo extends StatelessWidget {
  const BrandLogo({
    super.key,
    this.height = 28.0,
    this.width,
    this.fit = BoxFit.contain,
    this.semanticsLabel,
    this.locale,
  });

  /// Rendered height in logical pixels.
  final double height;

  /// Rendered width; if omitted, scales with the artwork aspect ratio.
  final double? width;

  /// Box fit for the image.
  final BoxFit fit;

  /// Semantics label for accessibility. Defaults to `common.brandName` from i18n.
  final String? semanticsLabel;

  /// Explicit locale override (e.g. 'en' or 'ar'). If omitted, resolved from context.
  final String? locale;

  /// Below 24 px tall, the full lockup is unreadable: brand rules call for the mark alone.
  static const double minLockupHeightPx = 24.0;

  @override
  Widget build(BuildContext context) {
    String effectiveLocale = locale ?? 'en';
    String label = semanticsLabel ?? 'ProcurePilot';

    final provider =
        context.dependOnInheritedWidgetOfExactType<ServiceProvider>();
    if (provider != null) {
      if (locale == null) {
        effectiveLocale = provider.i18n.locale;
      }
      label = semanticsLabel ?? provider.i18n.t('common.brandName');
    } else {
      final loc = Localizations.maybeLocaleOf(context);
      if (loc != null) {
        if (locale == null) {
          effectiveLocale = loc.languageCode;
        }
      } else if (Directionality.maybeOf(context) == TextDirection.rtl) {
        if (locale == null) {
          effectiveLocale = 'ar';
        }
      }
    }

    final String assetPath;
    if (height < minLockupHeightPx) {
      assetPath = 'assets/brand/procurepilot-mark-192px.png';
    } else if (effectiveLocale == 'ar') {
      assetPath = 'assets/brand/procurepilot-arabic-horizontal-1436px.png';
    } else {
      assetPath = 'assets/brand/procurepilot-horizontal-1436px.png';
    }

    // Clear space around any logo: at least the height of one bar of the mark (1/8 of the mark).
    final clearSpace = height / 8.0;

    return Semantics(
      label: label,
      image: true,
      child: Padding(
        padding: EdgeInsets.all(clearSpace),
        child: Directionality(
          textDirection: TextDirection.ltr,
          child: Image.asset(
            assetPath,
            height: height,
            width: width,
            fit: fit,
            matchTextDirection: false,
          ),
        ),
      ),
    );
  }
}
