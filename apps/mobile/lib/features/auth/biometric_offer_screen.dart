import 'package:flutter/material.dart';

import '../service_provider.dart';
import 'biometric_preference.dart';

/// Post-sign-in offer to enable biometric unlock for future launches.
class BiometricOfferScreen extends StatelessWidget {
  const BiometricOfferScreen({super.key});

  Future<void> _enable(BuildContext context) async {
    final services = ServiceProvider.of(context);
    await BiometricPreference(services.authService.storage).setEnabled(true);
    if (!context.mounted) return;
    await Navigator.of(context).pushReplacementNamed('/home');
  }

  Future<void> _decline(BuildContext context) async {
    if (!context.mounted) return;
    await Navigator.of(context).pushReplacementNamed('/home');
  }

  @override
  Widget build(BuildContext context) {
    final i18n = ServiceProvider.of(context).i18n;

    return Scaffold(
      appBar: AppBar(title: Text(i18n.t('common.brandName'))),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Spacer(),
              Icon(
                Icons.fingerprint,
                size: 64,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(height: 24),
              Text(
                i18n.t('auth.biometric.enableTitle'),
                style: Theme.of(context).textTheme.headlineSmall,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              Text(
                i18n.t('auth.biometric.enableMessage'),
                textAlign: TextAlign.center,
              ),
              const Spacer(),
              FilledButton(
                key: const Key('biometricEnableButton'),
                onPressed: () => _enable(context),
                child: Text(i18n.t('auth.biometric.enableButton')),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                key: const Key('biometricDeclineButton'),
                onPressed: () => _decline(context),
                child: Text(i18n.t('auth.biometric.declineButton')),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
