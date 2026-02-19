from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
    name: str = Field(..., min_length=1, max_length=100)


class FamilyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)


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
    email: EmailStr
    role: str = Field(default="member", pattern="^(admin|member)$")


class InviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    expires_at: datetime


class InviteCodeResponse(BaseModel):
    invite_code: str


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|member)$")


class MessageResponse(BaseModel):
    message: str
