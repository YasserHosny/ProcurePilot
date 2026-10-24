import 'package:flutter/material.dart';

/// Semantic colors for the ProcurePilot Ledger design system.
///
/// Follows docs/design/design-system.html and docs/brand/README.md.
class LedgerColors extends ThemeExtension<LedgerColors> {
  const LedgerColors({
    required this.navy,
    required this.teal,
    required this.tealText,
    required this.paper,
    required this.paperCard,
    required this.paperSunken,
    required this.paperBorder,
    required this.paperBorderStrong,
    required this.textStrong,
    required this.text,
    required this.textMuted,
    required this.success,
    required this.successContainer,
    required this.warning,
    required this.warningContainer,
    required this.error,
    required this.errorContainer,
    required this.info,
    required this.infoContainer,
    required this.savings,
    required this.savingsContainer,
    required this.savingsRule,
  });

  final Color navy;
  final Color teal;
  final Color tealText;
  final Color paper;
  final Color paperCard;
  final Color paperSunken;
  final Color paperBorder;
  final Color paperBorderStrong;
  final Color textStrong;
  final Color text;
  final Color textMuted;
  final Color success;
  final Color successContainer;
  final Color warning;
  final Color warningContainer;
  final Color error;
  final Color errorContainer;
  final Color info;
  final Color infoContainer;
  final Color savings;
  final Color savingsContainer;
  final Color savingsRule;

  static const light = LedgerColors(
    navy: Color(0xFF0B2545),
    teal: Color(0xFF12A594),
    tealText: Color(0xFF0C7A6E),
    paper: Color(0xFFF4F6F9),
    paperCard: Color(0xFFFFFFFF),
    paperSunken: Color(0xFFE8EDF3),
    paperBorder: Color(0xFFD2DAE4),
    paperBorderStrong: Color(0xFF8494A8),
    textStrong: Color(0xFF0B2545),
    text: Color(0xFF2A3B52),
    textMuted: Color(0xFF4F5F75),
    success: Color(0xFF166534),
    successContainer: Color(0xFFDCF2E3),
    warning: Color(0xFF8A4B00),
    warningContainer: Color(0xFFFBEBD3),
    error: Color(0xFFA3231B),
    errorContainer: Color(0xFFFBE4E1),
    info: Color(0xFF1D4ED8),
    infoContainer: Color(0xFFE0EAFB),
    savings: Color(0xFF0C7A6E),
    savingsContainer: Color(0xFFE7F6F3),
    savingsRule: Color(0xFF12A594),
  );

  @override
  LedgerColors copyWith({
    Color? navy,
    Color? teal,
    Color? tealText,
    Color? paper,
    Color? paperCard,
    Color? paperSunken,
    Color? paperBorder,
    Color? paperBorderStrong,
    Color? textStrong,
    Color? text,
    Color? textMuted,
    Color? success,
    Color? successContainer,
    Color? warning,
    Color? warningContainer,
    Color? error,
    Color? errorContainer,
    Color? info,
    Color? infoContainer,
    Color? savings,
    Color? savingsContainer,
    Color? savingsRule,
  }) {
    return LedgerColors(
      navy: navy ?? this.navy,
      teal: teal ?? this.teal,
      tealText: tealText ?? this.tealText,
      paper: paper ?? this.paper,
      paperCard: paperCard ?? this.paperCard,
      paperSunken: paperSunken ?? this.paperSunken,
      paperBorder: paperBorder ?? this.paperBorder,
      paperBorderStrong: paperBorderStrong ?? this.paperBorderStrong,
      textStrong: textStrong ?? this.textStrong,
      text: text ?? this.text,
      textMuted: textMuted ?? this.textMuted,
      success: success ?? this.success,
      successContainer: successContainer ?? this.successContainer,
      warning: warning ?? this.warning,
      warningContainer: warningContainer ?? this.warningContainer,
      error: error ?? this.error,
      errorContainer: errorContainer ?? this.errorContainer,
      info: info ?? this.info,
      infoContainer: infoContainer ?? this.infoContainer,
      savings: savings ?? this.savings,
      savingsContainer: savingsContainer ?? this.savingsContainer,
      savingsRule: savingsRule ?? this.savingsRule,
    );
  }

  @override
  LedgerColors lerp(ThemeExtension<LedgerColors>? other, double t) {
    if (other is! LedgerColors) return this;
    return LedgerColors(
      navy: Color.lerp(navy, other.navy, t)!,
      teal: Color.lerp(teal, other.teal, t)!,
      tealText: Color.lerp(tealText, other.tealText, t)!,
      paper: Color.lerp(paper, other.paper, t)!,
      paperCard: Color.lerp(paperCard, other.paperCard, t)!,
      paperSunken: Color.lerp(paperSunken, other.paperSunken, t)!,
      paperBorder: Color.lerp(paperBorder, other.paperBorder, t)!,
      paperBorderStrong: Color.lerp(paperBorderStrong, other.paperBorderStrong, t)!,
      textStrong: Color.lerp(textStrong, other.textStrong, t)!,
      text: Color.lerp(text, other.text, t)!,
      textMuted: Color.lerp(textMuted, other.textMuted, t)!,
      success: Color.lerp(success, other.success, t)!,
      successContainer: Color.lerp(successContainer, other.successContainer, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      warningContainer: Color.lerp(warningContainer, other.warningContainer, t)!,
      error: Color.lerp(error, other.error, t)!,
      errorContainer: Color.lerp(errorContainer, other.errorContainer, t)!,
      info: Color.lerp(info, other.info, t)!,
      infoContainer: Color.lerp(infoContainer, other.infoContainer, t)!,
      savings: Color.lerp(savings, other.savings, t)!,
      savingsContainer: Color.lerp(savingsContainer, other.savingsContainer, t)!,
      savingsRule: Color.lerp(savingsRule, other.savingsRule, t)!,
    );
  }
}
