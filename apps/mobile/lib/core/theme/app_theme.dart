import 'package:flutter/material.dart';

import 'brand_colors.dart';
import 'ledger_typography.dart';

/// ProcurePilot "Ledger" design system theme for Flutter.
///
/// Light mode only. Replicates the Angular Material 3 web theme
/// (`apps/web/src/styles.scss` and `apps/web/src/styles/_ledger-tokens.scss`).
class AppTheme {
  AppTheme._();

  static const Color primaryNavy = Color(0xFF0B2545);
  static const Color paperBackground = Color(0xFFF4F6F9);

  /// Explicit Material 3 ColorScheme built from web palette tones and overrides.
  /// Does not use [ColorScheme.fromSeed] because generated seed tones differ from the web.
  static const ColorScheme lightColorScheme = ColorScheme(
    brightness: Brightness.light,
    primary: Color(0xFF0B2545),
    onPrimary: Color(0xFFFFFFFF),
    primaryContainer: Color(0xFFDCE4EE),
    onPrimaryContainer: Color(0xFF0B2545),
    secondary: Color(0xFF0B2545),
    onSecondary: Color(0xFFFFFFFF),
    secondaryContainer: Color(0xFFDCE4EE),
    onSecondaryContainer: Color(0xFF0B2545),
    tertiary: Color(0xFF0C7A6E),
    onTertiary: Color(0xFFFFFFFF),
    tertiaryContainer: Color(0xFFE7F6F3),
    onTertiaryContainer: Color(0xFF0C7A6E),
    error: Color(0xFFA3231B),
    onError: Color(0xFFFFFFFF),
    errorContainer: Color(0xFFFBE4E1),
    onErrorContainer: Color(0xFFA3231B),
    surface: Color(0xFFF4F6F9),
    onSurface: Color(0xFF0B2545),
    onSurfaceVariant: Color(0xFF4F5F75),
    outline: Color(0xFF8494A8),
    outlineVariant: Color(0xFFD2DAE4),
    shadow: Color(0xFF0B2545),
    scrim: Color(0x8C061629),
    inverseSurface: Color(0xFF0B2545),
    onInverseSurface: Color(0xFFF4F6F9),
    inversePrimary: Color(0xFFC9D6E3),
    surfaceTint: Colors.transparent,
    surfaceBright: Color(0xFFFFFFFF),
    surfaceDim: Color(0xFFE8EDF3),
    surfaceContainerLowest: Color(0xFFFFFFFF),
    surfaceContainerLow: Color(0xFFFFFFFF),
    surfaceContainer: Color(0xFFFFFFFF),
    surfaceContainerHigh: Color(0xFFFFFFFF),
    surfaceContainerHighest: Color(0xFFE8EDF3),
  );

  /// Builds the light [ThemeData] matching the web Ledger design system.
  static ThemeData get lightTheme {
    const textTheme = TextTheme(
      displayLarge: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w600,
        color: Color(0xFF0B2545),
      ),
      displayMedium: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w600,
        color: Color(0xFF0B2545),
      ),
      displaySmall: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w600,
        color: Color(0xFF0B2545),
      ),
      headlineLarge: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w600,
        color: Color(0xFF0B2545),
      ),
      headlineMedium: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w600,
        color: Color(0xFF0B2545),
      ),
      headlineSmall: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w600,
        color: Color(0xFF0B2545),
      ),
      titleLarge: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w600,
        color: Color(0xFF0B2545),
      ),
      titleMedium: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w500,
        color: Color(0xFF0B2545),
      ),
      titleSmall: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w500,
        color: Color(0xFF0B2545),
      ),
      bodyLarge: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w400,
        color: Color(0xFF2A3B52),
      ),
      bodyMedium: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w400,
        color: Color(0xFF2A3B52),
      ),
      bodySmall: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w400,
        color: Color(0xFF4F5F75),
      ),
      labelLarge: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w500,
        color: Color(0xFF0B2545),
      ),
      labelMedium: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w500,
        color: Color(0xFF4F5F75),
      ),
      labelSmall: TextStyle(
        fontFamily: LedgerTypography.fontSans,
        fontWeight: FontWeight.w500,
        color: Color(0xFF4F5F75),
      ),
    );

    return ThemeData(
      useMaterial3: true,
      fontFamily: LedgerTypography.fontSans,
      colorScheme: lightColorScheme,
      scaffoldBackgroundColor: paperBackground,
      textTheme: textTheme,
      extensions: const [LedgerColors.light],
      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xFFFFFFFF),
        foregroundColor: Color(0xFF0B2545),
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontFamily: LedgerTypography.fontSans,
          color: Color(0xFF0B2545),
          fontSize: 18,
          fontWeight: FontWeight.w600,
        ),
        iconTheme: IconThemeData(color: Color(0xFF4F5F75)),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: const Color(0xFF0B2545),
          foregroundColor: const Color(0xFFFFFFFF),
          minimumSize: const Size(0, 36),
          padding: const EdgeInsets.symmetric(horizontal: 16),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          textStyle: const TextStyle(
            fontFamily: LedgerTypography.fontSans,
            fontWeight: FontWeight.w500,
            fontSize: 14,
          ),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF0B2545),
          foregroundColor: const Color(0xFFFFFFFF),
          elevation: 0,
          minimumSize: const Size(0, 36),
          padding: const EdgeInsets.symmetric(horizontal: 16),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          textStyle: const TextStyle(
            fontFamily: LedgerTypography.fontSans,
            fontWeight: FontWeight.w500,
            fontSize: 14,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: const Color(0xFF0B2545),
          backgroundColor: const Color(0xFFFFFFFF),
          side: const BorderSide(color: Color(0xFF8494A8)),
          minimumSize: const Size(0, 36),
          padding: const EdgeInsets.symmetric(horizontal: 16),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          textStyle: const TextStyle(
            fontFamily: LedgerTypography.fontSans,
            fontWeight: FontWeight.w500,
            fontSize: 14,
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: const Color(0xFF0B2545),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          textStyle: const TextStyle(
            fontFamily: LedgerTypography.fontSans,
            fontWeight: FontWeight.w500,
            fontSize: 14,
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFFFFFFFF),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: Color(0xFF8494A8)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: Color(0xFF8494A8)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: Color(0xFF0B2545), width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: Color(0xFFA3231B)),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: Color(0xFFA3231B), width: 2),
        ),
        labelStyle: const TextStyle(
          color: Color(0xFF4F5F75),
          fontFamily: LedgerTypography.fontSans,
          fontSize: 14,
        ),
        floatingLabelStyle: const TextStyle(
          color: Color(0xFF0B2545),
          fontFamily: LedgerTypography.fontSans,
          fontSize: 14,
        ),
        hintStyle: const TextStyle(
          color: Color(0xFF4F5F75),
          fontFamily: LedgerTypography.fontSans,
          fontSize: 14,
        ),
      ),
      cardTheme: CardThemeData(
        color: const Color(0xFFFFFFFF),
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
          side: const BorderSide(color: Color(0xFFD2DAE4), width: 1),
        ),
        margin: const EdgeInsets.symmetric(vertical: 4),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: const Color(0xFFFFFFFF),
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(4),
          side: const BorderSide(color: Color(0xFFD2DAE4)),
        ),
        labelStyle: const TextStyle(
          fontFamily: LedgerTypography.fontSans,
          fontSize: 12,
          color: Color(0xFF2A3B52),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 0),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: const Color(0xFFFFFFFF),
        surfaceTintColor: Colors.transparent,
        elevation: 3,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
        titleTextStyle: const TextStyle(
          fontFamily: LedgerTypography.fontSans,
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: Color(0xFF0B2545),
        ),
        contentTextStyle: const TextStyle(
          fontFamily: LedgerTypography.fontSans,
          fontSize: 14,
          color: Color(0xFF2A3B52),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: const Color(0xFF0B2545),
        contentTextStyle: const TextStyle(
          fontFamily: LedgerTypography.fontSans,
          color: Color(0xFFF4F6F9),
          fontSize: 14,
        ),
        actionTextColor: const Color(0xFFC9D6E3),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(6),
        ),
      ),
      listTileTheme: const ListTileThemeData(
        textColor: Color(0xFF0B2545),
        iconColor: Color(0xFF4F5F75),
        titleTextStyle: TextStyle(
          fontFamily: LedgerTypography.fontSans,
          fontSize: 14,
          fontWeight: FontWeight.w500,
          color: Color(0xFF0B2545),
        ),
        subtitleTextStyle: TextStyle(
          fontFamily: LedgerTypography.fontSans,
          fontSize: 12,
          color: Color(0xFF4F5F75),
        ),
      ),
      dividerTheme: const DividerThemeData(
        color: Color(0xFFD2DAE4),
        thickness: 1,
        space: 16,
      ),
    );
  }
}
