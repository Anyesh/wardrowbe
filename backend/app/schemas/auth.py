from uuid import UUID

from pydantic import BaseModel

IDENTITY_TOKEN = "identity"


class TokenPayload(BaseModel):
    # sub is the user id and iid the identity the token was minted for when sub_type is
    # IDENTITY_TOKEN; tokens minted before identities existed carry no sub_type and the
    # user's external_id as sub.
    sub: str
    exp: int
    iat: int | None = None
    iid: str | None = None
    sub_type: str | None = None
    email: str | None = None
    name: str | None = None


class AuthSession(BaseModel):
    user_id: UUID
    external_id: str | None
    email: str
    display_name: str
    family_id: UUID | None = None
    role: str
    is_authenticated: bool = True
