import 'package:flutter/material.dart';

import '../../core/i18n/i18n_loader.dart';
import '../../core/platform/link_opener.dart';
import '../../core/platform/version_provider.dart';
import '../service_provider.dart';

/// "Help & about" screen (Jira PPS-74).
///
/// Displays support contact, legal policy links, company attribution, and
/// app version. External links and mailto actions are dispatched through
/// [LinkOpener].
class AboutScreen extends StatefulWidget {
  const AboutScreen({
    super.key,
    this.linkOpener,
    this.versionProvider,
    this.webOrigin,
  });

  final LinkOpener? linkOpener;
  final AppVersionProvider? versionProvider;
  final String? webOrigin;

  @override
  State<AboutScreen> createState() => _AboutScreenState();
}

class _AboutScreenState extends State<AboutScreen> {
  String _version = '';
  bool _versionLoaded = false;

  I18nLoader get _i18n => ServiceProvider.maybeOf(context)?.i18n ?? I18nLoader();

  LinkOpener get _linkOpener =>
      widget.linkOpener ??
      ServiceProvider.maybeOf(context)?.linkOpener ??
      const UrlLauncherLinkOpener();

  String get _webOrigin {
    final raw = widget.webOrigin ??
        ServiceProvider.maybeOf(context)?.webOrigin ??
        const String.fromEnvironment(
          'WEB_ORIGIN',
          defaultValue: 'https://procurepilot.iron-sys.com',
        );
    return raw.endsWith('/') ? raw.substring(0, raw.length - 1) : raw;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_versionLoaded) {
      _versionLoaded = true;
      _loadVersion();
    }
  }

  Future<void> _loadVersion() async {
    final provider = widget.versionProvider ??
        ServiceProvider.maybeOf(context)?.versionProvider ??
        const PackageInfoVersionProvider();
    final version = await provider.getVersionString();
    if (mounted) {
      setState(() {
        _version = version;
      });
    }
  }

  Future<void> _openLink(String url) async {
    await _linkOpener.open(Uri.parse(url));
  }

  @override
  Widget build(BuildContext context) {
    final i18n = _i18n;
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(i18n.t('about.title')),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsetsDirectional.symmetric(vertical: 8),
                children: [
                  ListTile(
                    key: const Key('aboutContactSupportTile'),
                    leading: const Icon(Icons.mail_outline),
                    title: Text(i18n.t('about.support')),
                    subtitle: Text(i18n.t('about.supportHint')),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => _openLink('mailto:support@iron-sys.com'),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    key: const Key('aboutPrivacyPolicyTile'),
                    leading: const Icon(Icons.privacy_tip_outlined),
                    title: Text(i18n.t('about.privacy')),
                    trailing: const Icon(Icons.open_in_new, size: 18),
                    onTap: () => _openLink('$_webOrigin/privacy'),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    key: const Key('aboutTermsOfServiceTile'),
                    leading: const Icon(Icons.description_outlined),
                    title: Text(i18n.t('about.terms')),
                    trailing: const Icon(Icons.open_in_new, size: 18),
                    onTap: () => _openLink('$_webOrigin/terms'),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.only(
                start: 16,
                end: 16,
                bottom: 24,
                top: 8,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Semantics(
                    button: true,
                    label:
                        '${i18n.t('about.productByPrefix')} ${i18n.t('about.companyName')} ${i18n.t('about.companyLink')}',
                    child: InkWell(
                      key: const Key('aboutCompanyLink'),
                      borderRadius: BorderRadius.circular(8),
                      onTap: () => _openLink('https://www.iron-sys.com/'),
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(minHeight: 48),
                        child: Padding(
                          padding: const EdgeInsetsDirectional.symmetric(
                            horizontal: 16,
                            vertical: 8,
                          ),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                '${i18n.t('about.productByPrefix')} ${i18n.t('about.companyName')}',
                                style: theme.textTheme.bodyMedium?.copyWith(
                                  fontWeight: FontWeight.w600,
                                ),
                                textAlign: TextAlign.center,
                              ),
                              const SizedBox(height: 4),
                              Directionality(
                                textDirection: TextDirection.ltr,
                                child: Text(
                                  i18n.t('about.companyLink'),
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: theme.colorScheme.primary,
                                    decoration: TextDecoration.underline,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  if (_version.isNotEmpty)
                    Text(
                      i18n.t('about.version', params: {'version': _version}),
                      key: const Key('aboutVersionText'),
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                      textAlign: TextAlign.center,
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
