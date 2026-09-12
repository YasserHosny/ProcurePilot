import 'package:flutter/material.dart';

import '../../core/auth/auth_service.dart';
import '../../core/auth/biometric_gate.dart';
import '../../core/i18n/i18n_loader.dart';
import '../service_provider.dart';

/// Credential sign-in screen.
///
/// On success, the member is offered biometric unlock if the device supports
/// it; otherwise they proceed straight to the home screen.
class SignInScreen extends StatefulWidget {
  const SignInScreen({super.key});

  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<SignInScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  bool _isLoading = false;
  bool _obscurePassword = true;
  String? _errorText;

  AuthService get _authService => ServiceProvider.of(context).authService;
  BiometricGate get _biometricGate => ServiceProvider.of(context).biometricGate;
  I18nLoader get _i18n => ServiceProvider.of(context).i18n;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() {
      _isLoading = true;
      _errorText = null;
    });

    try {
      await _authService.signIn(
        _emailController.text.trim(),
        _passwordController.text,
      );

      if (!mounted) return;

      _syncApiTokens();

      final biometricAvailable = await _biometricGate.biometricAuth
          .isAvailable();
      if (!mounted) return;

      if (biometricAvailable) {
        await Navigator.of(context).pushReplacementNamed('/biometricOffer');
      } else {
        await Navigator.of(context).pushReplacementNamed('/home');
      }
    } on AuthException catch (e) {
      if (!mounted) return;
      setState(() => _errorText = _translatedAuthError(e));
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _syncApiTokens() {
    final services = ServiceProvider.of(context);
    final token = services.authService.accessToken;
    services.mobileApiClient.accessToken = token;
    services.approvalsApiClient.accessToken = token;
  }

  String? _emailValidator(String? value) {
    final trimmed = value?.trim() ?? '';
    if (trimmed.isEmpty) return _i18n.t('auth.signin.emailRequired');
    if (!trimmed.contains('@')) return _i18n.t('auth.signin.emailInvalid');
    return null;
  }

  String? _passwordValidator(String? value) {
    if (value == null || value.isEmpty) {
      return _i18n.t('auth.signin.passwordRequired');
    }
    return null;
  }

  /// Maps a sign-in failure to a translated `auth.signin.*Error` key rather than showing
  /// [AuthException.message] verbatim — that's Supabase's own untranslated `error_description`,
  /// which bypassed `packages/i18n` entirely for Arabic sessions (PR review finding). Supabase
  /// Auth's `/auth/v1/token` returns 400 for invalid credentials (not 401 — mobile talks to
  /// Supabase Auth directly, unlike web's apps/api proxy which does use 401 for the same case)
  /// and 429 for rate limiting.
  String _translatedAuthError(AuthException e) {
    switch (e.statusCode) {
      case 400:
        return _i18n.t('auth.signin.invalidCredentialsError');
      case 429:
        return _i18n.t('auth.signin.rateLimitedError');
      default:
        return _i18n.t('auth.signin.genericError');
    }
  }

  @override
  Widget build(BuildContext context) {
    final i18n = _i18n;

    return Scaffold(
      appBar: AppBar(title: Text(i18n.t('common.brandName'))),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: ListView(
              children: [
                Text(
                  i18n.t('auth.signin.title'),
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 8),
                Text(i18n.t('auth.signin.subtitle')),
                const SizedBox(height: 24),
                TextFormField(
                  key: const Key('signInEmailField'),
                  controller: _emailController,
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                  decoration: InputDecoration(
                    labelText: i18n.t('auth.signin.emailLabel'),
                    hintText: i18n.t('auth.signin.emailPlaceholder'),
                  ),
                  validator: _emailValidator,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  key: const Key('signInPasswordField'),
                  controller: _passwordController,
                  obscureText: _obscurePassword,
                  textInputAction: TextInputAction.done,
                  onFieldSubmitted: (_) => _submit(),
                  decoration: InputDecoration(
                    labelText: i18n.t('auth.signin.passwordLabel'),
                    hintText: i18n.t('auth.signin.passwordPlaceholder'),
                    suffixIcon: IconButton(
                      icon: Icon(
                        _obscurePassword
                            ? Icons.visibility
                            : Icons.visibility_off,
                      ),
                      onPressed: () =>
                          setState(() => _obscurePassword = !_obscurePassword),
                      tooltip: _obscurePassword
                          ? i18n.t('auth.signin.showPassword')
                          : i18n.t('auth.signin.hidePassword'),
                    ),
                  ),
                  validator: _passwordValidator,
                ),
                if (_errorText != null) ...[
                  const SizedBox(height: 16),
                  Text(
                    _errorText!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ],
                const SizedBox(height: 24),
                ElevatedButton(
                  key: const Key('signInSubmitButton'),
                  onPressed: _isLoading ? null : _submit,
                  child: Text(
                    _isLoading
                        ? i18n.t('auth.signin.submittingButton')
                        : i18n.t('auth.signin.submitButton'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
