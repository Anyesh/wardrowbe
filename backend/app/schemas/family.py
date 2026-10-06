from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.email import EmailAddress
from app.schemas.text import SingleLineText


class FamilyMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    email: str
    avatar_url: str | None = None
    role: str
    created_at: datetime


class PendingInvite(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    created_at: datetime
    expires_at: datetime


class FamilyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    invite_code: str
    members: list[FamilyMember] = []
    pending_invites: list[PendingInvite] = []
    created_at: datetime


class FamilyCreate(BaseModel):
    name: SingleLineText = Field(..., min_length=1, max_length=100)


class FamilyUpdate(BaseModel):
    name: SingleLineText | None = Field(None, min_length=1, max_length=100)


class FamilyCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    invite_code: str
    role: str = "admin"


class JoinFamilyRequest(BaseModel):
    invite_code: str = Field(..., min_length=1, max_length=20)


class JoinByTokenRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=100)


class JoinFamilyResponse(BaseModel):
    family_id: UUID
    family_name: str
    role: str = "member"


class InviteMemberRequest(BaseModel):
    email: EmailAddress
    role: str = Field(default="member", pattern="^(admin|member)$")


class InviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    expires_at: datetime
    # False when SMTP is unconfigured or the send failed, so the inviter knows to share the code.
    email_sent: bool


class InviteCodeResponse(BaseModel):
    invite_code: str


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|member)$")


class MessageResponse(BaseModel):
    message: str
