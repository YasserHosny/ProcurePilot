import 'package:flutter/material.dart';

import 'core/i18n/i18n_loader.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final i18n = I18nLoader();
  await i18n.load(const String.fromEnvironment('DEFAULT_LOCALE', defaultValue: 'en'));
  runApp(ProcurePilotApp(i18n: i18n));
}

class ProcurePilotApp extends StatelessWidget {
  const ProcurePilotApp({super.key, required this.i18n});

  final I18nLoader i18n;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: i18n,
      builder: (context, _) {
        return MaterialApp(
          title: i18n.t('common.brandName'),
          locale: Locale(i18n.locale),
          builder: (context, child) {
            return Directionality(
              textDirection: i18n.textDirection,
              child: child ?? const SizedBox.shrink(),
            );
          },
          home: const Scaffold(
            body: Center(child: Text('Hello World')),
          ),
        );
      },
    );
  }
}
