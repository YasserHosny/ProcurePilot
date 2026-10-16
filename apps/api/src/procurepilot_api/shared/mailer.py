import os
import uuid
from email.utils import formataddr
from typing import Protocol

import httpx
from pydantic import BaseModel

from procurepilot_api.config import get_settings


class SendResult(BaseModel):
    message_id: str


class Mailer(Protocol):
    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        headers: dict[str, str] | None = None,
        html: str | None = None,
        from_name: str | None = None,
    ) -> SendResult: ...


class FakeMessage(BaseModel):
    to: str
    subject: str
    body: str
    headers: dict[str, str] | None
    message_id: str
    html: str | None = None
    from_name: str | None = None


class FakeMailer:
    sent_messages: list[FakeMessage] = []

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        headers: dict[str, str] | None = None,
        html: str | None = None,
        from_name: str | None = None,
    ) -> SendResult:
        # Deterministic-enough fake Message-ID
        msg_id = f"fake-{uuid.uuid4().hex}@stub.mail"
        self.sent_messages.append(
            FakeMessage(
                to=to,
                subject=subject,
                body=body,
                headers=headers,
                message_id=msg_id,
                html=html,
                from_name=from_name,
            )
        )
        return SendResult(message_id=msg_id)

    @classmethod
    def clear(cls) -> None:
        cls.sent_messages.clear()


class MailgunMailer:
    def __init__(self) -> None:
        settings = get_settings()
        if settings.mailgun_api_key:
            self.api_key = settings.mailgun_api_key.get_secret_value()
        else:
            self.api_key = ""
        self.domain = settings.mailgun_sending_domain or ""
        self.api_url = f"https://api.mailgun.net/v3/{self.domain}/messages"

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        headers: dict[str, str] | None = None,
        html: str | None = None,
        from_name: str | None = None,
    ) -> SendResult:
        if not self.api_key or not self.domain:
            raise RuntimeError("Mailgun credentials not configured")

        data = {
            "from": formataddr(
                (from_name or "ProcurePilot", f"noreply@{self.domain}"), charset="utf-8"
            ),
            "to": [to],
            "subject": subject,
            "text": body,
        }
        if html is not None:
            data["html"] = html

        if headers:
            for k, v in headers.items():
                data[f"h:{k}"] = v

        response = httpx.post(
            self.api_url,
            auth=("api", self.api_key),
            data=data,
            timeout=10.0,
        )
        response.raise_for_status()

        result_json = response.json()
        return SendResult(message_id=result_json.get("id", str(uuid.uuid4())))


def get_mailer() -> Mailer:
    """Return the configured mailer.

    RFQ_MAILER_MODE=stub (default in tests/CI) -> FakeMailer.
    RFQ_MAILER_MODE=mailgun -> MailgunMailer.
    Mirrors get_intent_provider's own convention exactly.
    """
    mode = os.environ.get("RFQ_MAILER_MODE", "stub")
    if mode == "mailgun":
        return MailgunMailer()
    return FakeMailer()
