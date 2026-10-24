from __future__ import annotations

from uuid import UUID

from gotrue.errors import AuthApiError
from supabase import Client, create_client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import resolve_member_from_token
from procurepilot_api.errors import (
    AuthenticationError,
    InvalidCredentialsError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.members.models import SessionResponse
from procurepilot_api.modules.members.service import load_me_for_token

# The web page that receives the emailed recovery link and sets the new password. Its full URL
# must be in the Supabase Auth redirect allow list, or Supabase falls back to the Site URL.
PASSWORD_UPDATE_PATH = "/auth/update-password"


class AuthService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_auth_user(self, *, email: str, password: str) -> UUID:
        try:
            response = self._client().auth.sign_up({"email": email, "password": password})
        except Exception as exc:
            raise InvalidCredentialsError(details={"reason": "signup_refused"}) from exc
        return _extract_user_id(response)

    def login(self, *, email: str, password: str) -> SessionResponse:
        try:
            response = self._client().auth.sign_in_with_password(
                {"email": email, "password": password}
            )
        except Exception as exc:
            raise InvalidCredentialsError(details={"reason": "invalid_credentials"}) from exc
        return self.session_response(response)

    def reissue_session(self, *, refresh_token: str) -> SessionResponse:
        try:
            response = self._client().auth.refresh_session(refresh_token)
        except AuthApiError as exc:
            if exc.status in {400, 401, 403, 422}:
                raise AuthenticationError(details={"reason": "session_refresh_failed"}) from exc
            raise ServiceUnavailableError(details={"dependency": "supabase_auth"}) from exc
        except Exception as exc:
            # Network failures, rate limits and upstream outages do not reject the token.
            raise ServiceUnavailableError(details={"dependency": "supabase_auth"}) from exc
        return self.session_response(response)

    def logout(self, *, access_token: str, refresh_token: str | None) -> None:
        try:
            client = self._client()
            if refresh_token:
                client.auth.set_session(access_token, refresh_token)
            client.auth.sign_out()
        except Exception as exc:
            raise AuthenticationError(details={"reason": "logout_failed"}) from exc

    def request_password_reset(self, *, email: str) -> None:
        origin = self._settings.web_origin or self._settings.api_cors_origins[0]
        redirect_to = f"{origin.rstrip('/')}{PASSWORD_UPDATE_PATH}"
        try:
            self._client().auth.reset_password_email(email, {"redirect_to": redirect_to})
        except Exception:
            return

    def update_password(self, *, access_token: str, refresh_token: str, password: str) -> str:
        """Set a new password with the recovery session from the emailed link.

        Returns the account's email for the audit trail.
        """
        try:
            client = self._client()
            client.auth.set_session(access_token, refresh_token)
            response = client.auth.update_user({"password": password})
        except AuthApiError as exc:
            if exc.status in {400, 401, 403}:
                raise AuthenticationError(details={"reason": "recovery_link_invalid"}) from exc
            if exc.status == 422:
                raise UnprocessableEntityError(
                    details={"reason": exc.code or "password_refused"}
                ) from exc
            raise ServiceUnavailableError(details={"dependency": "supabase_auth"}) from exc
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "supabase_auth"}) from exc
        return str(_attribute(_attribute(response, "user"), "email") or "")

    def session_response(self, response: object) -> SessionResponse:
        session = _extract_session(response)
        access_token = _required_string(session, "access_token")
        refresh_token = _required_string(session, "refresh_token")
        expires_in = _optional_int(session, "expires_in")
        member = resolve_member_from_token(access_token, self._settings)
        me = load_me_for_token(self._settings, access_token, member)
        return SessionResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            user=me,
        )

    def _client(self) -> Client:
        try:
            return create_client(
                self._settings.supabase_url,
                self._settings.supabase_anon_key.get_secret_value(),
            )
        except Exception as exc:
            raise ServiceUnavailableError(details={"dependency": "supabase_auth"}) from exc


def _extract_user_id(response: object) -> UUID:
    user = _attribute(response, "user") or _attribute(_attribute(response, "session"), "user")
    user_id = _attribute(user, "id")
    if user_id is None:
        raise InvalidCredentialsError(details={"reason": "missing_auth_user"})
    return UUID(str(user_id))


def _extract_session(response: object) -> object:
    session = _attribute(response, "session")
    if session is None:
        raise AuthenticationError(details={"reason": "missing_session"})
    return session


def _required_string(source: object, name: str) -> str:
    value = _attribute(source, name)
    if not isinstance(value, str) or not value:
        raise AuthenticationError(details={"reason": f"missing_{name}"})
    return value


def _optional_int(source: object, name: str) -> int | None:
    value = _attribute(source, name)
    if value is None:
        return None
    return int(value)


def _attribute(source: object | None, name: str) -> object | None:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def get_auth_service() -> AuthService:
    return AuthService()
