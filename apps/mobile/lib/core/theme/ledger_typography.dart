import 'package:flutter/material.dart';

/// Typography definitions and text style helpers for ProcurePilot Ledger design system.
///
/// Follows docs/brand/README.md and docs/design/design-system.html:
/// - Primary font family: Readex Pro (weights 400, 500, 600).
/// - Tabular figures font family: Noto Kufi Arabic with [FontFeature.tabularFigures()],
///   used specifically where digits must align vertically (amounts, quantities, money).
class LedgerTypography {
  static const String fontSans = 'Readex Pro';
  static const String fontFigures = 'Noto Kufi Arabic';

  /// Text style for tabular figures (money, quantities, amounts).
  ///
  /// Readex Pro has no tabular figures, so Noto Kufi Arabic with
  /// FontFeature.tabularFigures() is used where figures must align vertically.
  static TextStyle tabularFigures({
    double? fontSize,
    FontWeight? fontWeight,
    Color? color,
    double? height,
    TextBaseline? textBaseline,
  }) {
    return TextStyle(
      fontFamily: fontFigures,
      fontFeatures: const [FontFeature.tabularFigures()],
      fontSize: fontSize,
      fontWeight: fontWeight,
      color: color,
      height: height,
      textBaseline: textBaseline,
    );
  }
}
