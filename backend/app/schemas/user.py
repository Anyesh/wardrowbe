from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app.schemas.email import EmailAddress
from app.schemas.text import SingleLineName, SingleLineText, flatten_control_characters, is_blank
from app.utils.locale import DEFAULT_LOCALE

DISPLAY_NAME_MAX_LENGTH = 100
AVATAR_URL_MAX_LENGTH = 500

DisplayName = Annotated[SingleLineName, Field(min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH)]
Latitude = Annotated[Decimal, Field(ge=-90, le=90)]
Longitude = Annotated[Decimal, Field(ge=-180, le=180)]
PlaceName = Annotated[SingleLineText, Field(max_length=100)]


# The IdP owns this name and a refusal would lock the user out on every login, so it is flattened
# and cut to the column width instead of being refused.
def _fit_idp_display_name(value: object) -> object:
    flattened = flatten_control_characters(value)
    if not isinstance(flattened, str):
        return flattened
    if is_blank(flattened):
        return ""
    return flattened[:DISPLAY_NAME_MAX_LENGTH].rstrip()


# A cut URL would point nowhere, and refusing would lock the user out, so an avatar URL wider
# than the column is dropped.
def _drop_overlong_avatar_url(value: object) -> object:
    if isinstance(value, str) and len(value) > AVATAR_URL_MAX_LENGTH:
        return None
    return value


class UserBase(BaseModel):
    # Plain str because responses must not fail on a detached account's reserved-TLD address.
    email: str
    display_name: str = Field(..., min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH)
    avatar_url: str | None = None
    timezone: str = Field(default="UTC", max_length=50)
    locale: str = Field(default=DEFAULT_LOCALE, max_length=10)
    location_lat: Latitude | None = None
    location_lon: Longitude | None = None
    # Plain str so that a place stored before line breaks were refused still reads back.
    location_name: str | None = Field(None, max_length=100)


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str
    family_id: UUID | None = None
    role: str
    is_active: bool
    onboarding_completed: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserSyncRequest(BaseModel):
    external_id: str = Field(
        ..., min_length=1, max_length=255, description="Subject ID from OIDC provider"
    )
    email: EmailAddress | None = Field(
        None, description="Email address; derived from ID token when omitted"
    )
    display_name: Annotated[str, BeforeValidator(_fit_idp_display_name)]
    avatar_url: Annotated[str | None, BeforeValidator(_drop_overlong_avatar_url)] = None
    id_token: str | None = Field(
        None, description="OIDC ID token for verification (required when OIDC is configured)"
    )
    provider: str | None = Field(None, description="Auth provider (e.g. 'oidc'), omit for default")

    # Mirrors the web client's fallback (frontend/lib/auth.ts) so that the stored name does not
    # depend on which client signed in. Without an email the name stays blank because the OIDC
    # path fills the email from the token and validates again.
    @model_validator(mode="after")
    def _name_or_email_local_part(self) -> "UserSyncRequest":
        if not self.display_name and self.email:
            self.display_name = self.email.split("@")[0]
        return self


class UserSyncResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    is_new_user: bool
    onboarding_completed: bool
    access_token: str = Field(..., description="JWT token for API authentication")


class SessionUser(BaseModel):
    id: UUID
    external_id: str
    email: str
    display_name: str
    family_id: UUID | None = None
    role: str


class AuthStatusResponse(BaseModel):
    configured: bool
    mode: str
    error: str | None = None


class AuthConfigOIDC(BaseModel):
    enabled: bool
    issuer_url: str | None = None
    client_id: str | None = None


class AuthConfigResponse(BaseModel):
    oidc: AuthConfigOIDC
    dev_mode: bool = False
