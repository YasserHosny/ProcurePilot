import 'package:flutter/material.dart';

import '../../core/api/approvals_api_client.dart';
import '../../core/auth/auth_service.dart';
import '../../core/i18n/i18n_loader.dart';
import '../auth/auth_session.dart';
import '../auth/biometric_preference.dart';
import '../auth/device_registrar.dart';
import '../service_provider.dart';

/// Role-aware home screen.
///
/// - Request-capable roles (owner, buyer, branch_manager) see a primary
///   "Request items" action. The actual request-submission flow is Phase 4;
///   the button is currently disabled/placeholder.
/// - Approvers additionally see a read-only count of pending decisions from
///   [GET /approvals/pending]. No approve/reject control is rendered.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int? _pendingCount;
  bool _pendingCountLoading = false;
  String? _pendingCountError;

  AuthService get _authService => ServiceProvider.of(context).authService;
  ApprovalsApiClient get _approvalsApiClient =>
      ServiceProvider.of(context).approvalsApiClient;
  I18nLoader get _i18n => ServiceProvider.of(context).i18n;

  bool _pendingCountLoaded = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_pendingCountLoaded) {
      _pendingCountLoaded = true;
      final session = _session;
      if (session?.isApprover ?? false) {
        _loadPendingCount(session!);
      }
    }
  }

  Future<void> _loadPendingCount(MemberSession session) async {
    setState(() => _pendingCountLoading = true);

    try {
      // Pilot-scale simplification: count only the first page, capped at 100.
      // Exhaustive pagination is unnecessary because a single approver is not
      // expected to have more than 100 pending requests at once in this phase.
      final list = await _approvalsApiClient.listPendingApprovals();
      if (!mounted) return;
      setState(() {
        _pendingCount = list.items.length;
        _pendingCountError = null;
      });
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() {
        _pendingCountError = _i18n.t('mobileHome.pendingCountError');
      });
      debugPrint('Failed to load pending approvals count: $e');
    } finally {
      if (mounted) setState(() => _pendingCountLoading = false);
    }
  }

  MemberSession? get _session {
    final routeArgs = ModalRoute.of(context)?.settings.arguments;
    if (routeArgs is MemberSession) return routeArgs;
    final role = parseMemberSession(_authService.accessToken ?? '')?.role;
    return role != null ? MemberSession(role: role) : null;
  }

  Future<void> _signOut() async {
    final services = ServiceProvider.of(context);
    await _authService.signOut(
      deviceRegistrar: MobileDeviceRegistrar(services.mobileApiClient),
    );
    await BiometricPreference(_authService.storage).clear();
    if (!mounted) return;
    await Navigator.of(context).pushReplacementNamed('/signIn');
  }

  @override
  Widget build(BuildContext context) {
    final i18n = _i18n;
    final session = _session;
    final role = session?.role;
    final roleLabel = i18n.t('common.roles.${role ?? 'viewer'}');
    final canRequest = session?.canRequestItems ?? false;
    final isApprover = session?.isApprover ?? false;

    return Scaffold(
      appBar: AppBar(
        title: Text(i18n.t('mobileHome.title')),
        actions: [
          IconButton(
            key: const Key('signOutButton'),
            icon: const Icon(Icons.logout),
            tooltip: i18n.t('mobileHome.signOut'),
            onPressed: _signOut,
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(roleLabel, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 24),
              if (canRequest)
                ElevatedButton.icon(
                  key: const Key('homeRequestItemsButton'),
                  icon: const Icon(Icons.add_shopping_cart),
                  label: Text(i18n.t('mobileHome.requestItems')),
                  onPressed: () => Navigator.of(context).pushNamed('/requests/new'),
                ),
              if (isApprover) ...[
                const SizedBox(height: 24),
                _PendingCountWidget(
                  count: _pendingCount,
                  loading: _pendingCountLoading,
                  error: _pendingCountError,
                  i18n: i18n,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _PendingCountWidget extends StatelessWidget {
  const _PendingCountWidget({
    required this.count,
    required this.loading,
    required this.error,
    required this.i18n,
  });

  final int? count;
  final bool loading;
  final String? error;
  final I18nLoader i18n;

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (error != null) {
      return Text(
        error!,
        style: TextStyle(color: Theme.of(context).colorScheme.error),
      );
    }

    final displayCount = count ?? 0;
    return Card(
      key: const Key('pendingApprovalsCount'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text(
          i18n.t(
            'mobileHome.pendingApprovalsCount',
            params: {'count': displayCount.toString()},
          ),
          style: Theme.of(context).textTheme.bodyLarge,
        ),
      ),
    );
  }
}
