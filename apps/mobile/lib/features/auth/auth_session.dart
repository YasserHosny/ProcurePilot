import 'dart:convert';

/// Member information extracted from the signed-in member's access token.
///
/// The access token is a Supabase JWT with custom claims shaped by the
/// `SupabaseClaims` model on the backend. This parser is intentionally
/// minimal: it reads only the claims the mobile UI needs for role-aware
/// rendering and does not verify the token (the API continues to verify it
/// on every request).
class MemberSession {
  const MemberSession({required this.role});

  final String role;

  /// Whether this member should see the Home screen's pending-decisions count.
  ///
  /// The backend's own `GET /approvals/pending` routes every pending step to the
  /// assigned approver, and ADDITIONALLY shows an owner every pending step in the
  /// tenant regardless of who it's assigned to (`RequestsService.list_pending_approvals`:
  /// owners are not filtered by `assigned_membership_id`). Restricting this to the literal
  /// 'approver' role hid the count from owners who can also decide requests — a delegate
  /// already holds the 'approver' role themselves, so delegation needs no separate check
  /// here (PR review finding).
  bool get isApprover => role == 'approver' || role == 'owner';

  /// Roles that can raise purchase requests from a branch context.
  bool get canRequestItems =>
      role == 'owner' || role == 'buyer' || role == 'branch_manager';
}

/// Parses the [member_role] claim from a Supabase access token.
///
/// Returns `null` if the token is not a valid JWT or contains no claim.
MemberSession? parseMemberSession(String accessToken) {
  try {
    final parts = accessToken.split('.');
    if (parts.length != 3) return null;

    var payload = parts[1];
    // JWT base64url may omit padding.
    final padding = 4 - payload.length % 4;
    if (padding != 4) {
      payload = payload.padRight(payload.length + padding, '=');
    }
    payload = payload.replaceAll('-', '+').replaceAll('_', '/');

    final decoded =
        jsonDecode(utf8.decode(base64Decode(payload))) as Map<String, dynamic>;

    final role = decoded['member_role'] as String?;
    if (role == null || role.isEmpty) return null;
    return MemberSession(role: role);
  } on FormatException {
    return null;
  } on ArgumentError {
    return null;
  }
}
