import pytest
from pydantic import ValidationError

from app.models.family import FamilyRole
from app.schemas.family import InviteMemberRequest, UpdateMemberRoleRequest


def test_invite_role_defaults_to_member():
    request = InviteMemberRequest(email="a@example.com")
    assert request.role == "member"


@pytest.mark.parametrize("role", ["admin", "member"])
def test_update_role_accepts_known_roles(role):
    assert UpdateMemberRoleRequest(role=role).role == FamilyRole(role)


@pytest.mark.parametrize("role", ["owner", "Admin", ""])
def test_update_role_rejects_unknown_roles(role):
    with pytest.raises(ValidationError):
        UpdateMemberRoleRequest(role=role)
    with pytest.raises(ValidationError):
        InviteMemberRequest(email="a@example.com", role=role)
