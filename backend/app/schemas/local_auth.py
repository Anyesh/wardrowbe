from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.email import EmailAddress
from app.schemas.text import SingleLineName
from app.schemas.user import DisplayName
from app.utils.passwords import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH

PASSKEY_NAME_MAX_LENGTH = 64

NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]
# A presented password is only bounded above, so that a too-short one reads as wrong rather
# than as a validation error that says something about the stored password.
PresentedPassword = Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]
PasskeyName = Annotated[SingleLineName, Field(min_length=1, max_length=PASSKEY_NAME_MAX_LENGTH)]


class SetupStatusResponse(BaseModel):
    required: bool


class SetupRequest(BaseModel):
    email: EmailAddress
    password: NewPassword
    display_name: DisplayName | None = None


class LoginRequest(BaseModel):
    # Plain str: a malformed address is just another failed sign-in, not a validation error.
    email: str = Field(..., min_length=1, max_length=320)
    password: PresentedPassword


class ReauthRequest(BaseModel):
    # Required when the account has a password; an account without one (OIDC) proves itself by a
    # recent sign-in instead.
    current_password: PresentedPassword | None = None


class ChangePasswordRequest(ReauthRequest):
    new_password: NewPassword


class AccessTokenResponse(BaseModel):
    access_token: str


class PasskeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None = None
    backed_up: bool
    transports: list[str]


class SecurityOverviewResponse(BaseModel):
    email: str
    local_auth_enabled: bool
    has_password: bool
    is_admin: bool
    passkeys: list[PasskeyResponse]


class PasskeyRegistrationVerifyRequest(BaseModel):
    name: PasskeyName
    # The RegistrationResponseJSON the browser produced; py_webauthn validates its structure.
    credential: dict[str, Any]


class PasskeyRenameRequest(BaseModel):
    name: PasskeyName


class PasskeyLoginOptionsResponse(BaseModel):
    flow_id: str
    options: dict[str, Any]


class PasskeyLoginVerifyRequest(BaseModel):
    flow_id: str = Field(..., min_length=1, max_length=128)
    credential: dict[str, Any]


class CreateLocalUserRequest(ReauthRequest):
    email: EmailAddress
    password: NewPassword
    display_name: DisplayName | None = None
    is_admin: bool = False


class LocalUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    is_admin: bool
    is_active: bool
    has_password: bool
    created_at: datetime
