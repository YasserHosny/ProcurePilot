from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class PasswordResetRequest(BaseModel):
    email: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class PasswordCredential(BaseModel):
    email: str
    password: str = Field(min_length=12)
