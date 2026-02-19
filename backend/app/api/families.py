import logging
import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.family import (
    FamilyCreate,
    FamilyCreateResponse,
    FamilyMember,
    FamilyResponse,
    FamilyUpdate,
    InviteCodeResponse,
    InviteMemberRequest,
    InviteResponse,
    JoinByTokenRequest,
    JoinFamilyRequest,
    JoinFamilyResponse,
    MessageResponse,
    PendingInvite,
    UpdateMemberRoleRequest,
)
from app.schemas.notification import EmailConfig
from app.services.family_service import FamilyService
from app.services.notification_providers import EmailProvider, build_family_invite_email
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/families", tags=["Families"])


def require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


def require_family_admin(user: User) -> None:
    if user.family_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not in a family",
        )
    require_admin(user)


@router.get("/me", response_model=FamilyResponse)
async def get_my_family(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FamilyResponse:
    if current_user.family_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not in a family",
        )

    family_service = FamilyService(db)
    family = await family_service.get_user_family(current_user)

    if family is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Family not found",
        )

    pending_invites = await family_service.get_pending_invites(family)

    return FamilyResponse(
        id=family.id,
        name=family.name,
        invite_code=family.invite_code,
        members=[
            FamilyMember(
                id=m.id,
                display_name=m.display_name,
                email=m.email,
                avatar_url=m.avatar_url,
                role=m.role,
                created_at=m.created_at,
            )
            for m in family.members
            if m.is_active
        ],
        pending_invites=[
            PendingInvite(
                id=i.id,
                email=i.email,
                created_at=i.created_at,
                expires_at=i.expires_at,
            )
            for i in pending_invites
        ],
        created_at=family.created_at,
    )


@router.post("", response_model=FamilyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_family(
    family_data: FamilyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FamilyCreateResponse:
    if current_user.family_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already in a family. Leave your current family first.",
        )

    family_service = FamilyService(db)
    family = await family_service.create(current_user, family_data)
    await db.commit()

    return FamilyCreateResponse(
        id=family.id,
        name=family.name,
        invite_code=family.invite_code,
        role="admin",
    )


@router.patch("/me", response_model=FamilyResponse)
async def update_family(
    family_data: FamilyUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FamilyResponse:
    require_family_admin(current_user)

    family_service = FamilyService(db)
    family = await family_service.get_user_family(current_user)

    if family is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Family not found",
        )

    family = await family_service.update(family, family_data)
    await db.commit()

    pending_invites = await family_service.get_pending_invites(family)

    return FamilyResponse(
        id=family.id,
        name=family.name,
        invite_code=family.invite_code,
        members=[
            FamilyMember(
                id=m.id,
                display_name=m.display_name,
                email=m.email,
                avatar_url=m.avatar_url,
                role=m.role,
                created_at=m.created_at,
            )
            for m in family.members
            if m.is_active
        ],
        pending_invites=[
            PendingInvite(
                id=i.id,
                email=i.email,
                created_at=i.created_at,
                expires_at=i.expires_at,
            )
            for i in pending_invites
        ],
        created_at=family.created_at,
    )


@router.post("/me/regenerate-code", response_model=InviteCodeResponse)
async def regenerate_invite_code(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> InviteCodeResponse:
    require_family_admin(current_user)

    family_service = FamilyService(db)
    family = await family_service.get_user_family(current_user)

    if family is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Family not found",
        )

    new_code = await family_service.regenerate_invite_code(family)
    await db.commit()

    return InviteCodeResponse(invite_code=new_code)


@router.post("/join", response_model=JoinFamilyResponse)
async def join_family(
    request: JoinFamilyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> JoinFamilyResponse:
    if current_user.family_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already in a family. Leave your current family first.",
        )

    family_service = FamilyService(db)
    family = await family_service.join_family(current_user, request.invite_code)

    if family is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invite code",
        )

    await db.commit()

    return JoinFamilyResponse(
        family_id=family.id,
        family_name=family.name,
        role="member",
    )


@router.post("/join-by-token", response_model=JoinFamilyResponse)
async def join_family_by_token(
    request: JoinByTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> JoinFamilyResponse:
    if current_user.family_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already in a family. Leave your current family first.",
        )

    family_service = FamilyService(db)
    invite = await family_service.get_invite_by_token(request.token)

    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invite link",
        )

    if invite.email.lower() != current_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invite was sent to a different email address",
        )

    family = await family_service.accept_invite_by_token(invite, current_user)
    await db.commit()

    if family is None:
        logger.error("Family %s not found after accepting invite %s", invite.family_id, invite.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Family not found",
        )

    return JoinFamilyResponse(
        family_id=family.id,
        family_name=family.name,
        role=current_user.role,
    )


@router.post("/me/leave", response_model=MessageResponse)
async def leave_family(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> MessageResponse:
    if current_user.family_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not in a family",
        )

    family_service = FamilyService(db)
    success = await family_service.leave_family(current_user)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot leave: you are the only admin. Transfer admin role first or remove all other members.",
        )

    await db.commit()
    return MessageResponse(message="Left family successfully")


@router.post("/me/invite", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    invite_data: InviteMemberRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> InviteResponse:
    require_family_admin(current_user)

    family_service = FamilyService(db)
    family = await family_service.get_user_family(current_user)

    if family is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Family not found",
        )

    invite = await family_service.create_invite(family, current_user, invite_data)
    await db.commit()

    app_url = os.getenv("APP_URL", "http://localhost:3000")
    provider = EmailProvider(EmailConfig(address=invite.email))
    if provider.is_configured():
        email = build_family_invite_email(
            to=invite.email,
            family_name=family.name,
            inviter_name=current_user.display_name,
            invite_token=invite.token,
            app_url=app_url,
        )
        result = await provider.send(email)
        if not result.get("success"):
            logger.warning("Failed to send family invite email: %s", result.get("error"))

    return InviteResponse(
        id=invite.id,
        email=invite.email,
        expires_at=invite.expires_at,
    )


@router.delete("/me/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invite(
    invite_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    require_family_admin(current_user)

    family_service = FamilyService(db)
    invite = await family_service.get_invite_by_id(invite_id)

    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found",
        )

    # Verify invite belongs to user's family
    if invite.family_id != current_user.family_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invite not found",
        )

    await family_service.cancel_invite(invite)
    await db.commit()


@router.patch("/me/members/{member_id}", response_model=FamilyMember)
async def update_member_role(
    member_id: UUID,
    request: UpdateMemberRoleRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FamilyMember:
    require_family_admin(current_user)

    if member_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    family_service = FamilyService(db)
    family = await family_service.get_user_family(current_user)

    if family is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Family not found",
        )

    member = await family_service.update_member_role(family, member_id, request.role)

    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in your family",
        )

    await db.commit()

    return FamilyMember(
        id=member.id,
        display_name=member.display_name,
        email=member.email,
        avatar_url=member.avatar_url,
        role=member.role,
        created_at=member.created_at,
    )


@router.delete("/me/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    member_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    require_family_admin(current_user)

    if member_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself. Use /leave instead.",
        )

    family_service = FamilyService(db)
    family = await family_service.get_user_family(current_user)

    if family is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Family not found",
        )

    success = await family_service.remove_member(family, member_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in your family",
        )

    await db.commit()
