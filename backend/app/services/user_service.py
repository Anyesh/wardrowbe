from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.schemas.user import UserSyncRequest

# Reserved by RFC 2606, so a detached address can never be delivered to or claimed by a sign-in.
DETACHED_EMAIL_DOMAIN = "detached.invalid"
EMAIL_IN_USE = "Email already in use by another account."
UNVERIFIED_EMAIL_IN_USE = (
    "Email already in use by another account. "
    "Sign in with a provider that verifies this address to use it."
)


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_external_id(
        self, external_id: str, load_preferences: bool = True
    ) -> User | None:
        query = select(User).where(User.external_id == external_id)

        if load_preferences:
            query = query.options(selectinload(User.preferences))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def sync_from_oidc(
        self, sync_data: UserSyncRequest, *, email_verified: bool
    ) -> tuple[User, bool]:
        """
        Sync user from OIDC provider.
        Creates user if not exists, updates if exists.
        Returns (user, is_new_user).

        email_verified states whether the caller's identity source vouched for sync_data.email,
        and is recorded on the user whenever its email is set.

        Migration behavior: If external_id doesn't match but email does,
        we update the external_id. This allows seamless migration between
        auth providers (e.g., TinyAuth forward-auth to direct Pocket ID OIDC).
        That takeover requires both the caller's email and the existing account's email
        to be verified. A verified caller whose email is held by an unverified account
        reclaims it instead: that account keeps its data under a detached placeholder
        address. Any other email clash raises UserEmailConflictError.
        """
        if sync_data.email.lower().endswith(f"@{DETACHED_EMAIL_DOMAIN}"):
            raise UserEmailConflictError(EMAIL_IN_USE)
        user = await self.get_by_external_id(sync_data.external_id)
        if user is not None:
            return await self._sign_in_existing(user, sync_data, email_verified), False
        try:
            return await self._sign_in_first_time(sync_data, email_verified)
        except IntegrityError:
            # Two first sign-ins for one identity or email race: the other request committed its
            # row after our lookups, so a second pass sees it and continues against it.
            user = await self.get_by_external_id(sync_data.external_id)
            if user is not None:
                return await self._sign_in_existing(user, sync_data, email_verified), False
            return await self._sign_in_first_time(sync_data, email_verified)

    async def _sign_in_first_time(
        self, sync_data: UserSyncRequest, email_verified: bool
    ) -> tuple[User, bool]:
        holder = await self.get_by_email(sync_data.email)
        if holder is None:
            return await self._insert_synced_user(sync_data, email_verified), True
        if holder.external_id == sync_data.external_id:
            # The caller's own row, committed by a concurrent first sign-in between the
            # external_id lookup and this one: not an adoption.
            return await self._sign_in_existing(holder, sync_data, email_verified), False
        if not email_verified:
            raise UserEmailConflictError(UNVERIFIED_EMAIL_IN_USE)
        if holder.email_verified:
            return await self._adopt(holder, sync_data), False
        return await self._insert_synced_user(sync_data, email_verified, reclaim_from=holder), True

    async def _sign_in_existing(
        self, user: User, sync_data: UserSyncRequest, email_verified: bool
    ) -> User:
        holder = None
        if user.email != sync_data.email:
            holder = await self.get_by_email(sync_data.email)
            if holder is not None and holder.email_verified:
                raise UserEmailConflictError(EMAIL_IN_USE)
            if holder is not None and not email_verified:
                raise UserEmailConflictError(UNVERIFIED_EMAIL_IN_USE)

        async with self._conflict_savepoint(EMAIL_IN_USE):
            if holder is not None:
                await self._detach_email(holder)
            if user.email != sync_data.email:
                user.email = sync_data.email
                user.email_verified = email_verified
            elif email_verified:
                user.email_verified = True
            user.display_name = sync_data.display_name
            if sync_data.avatar_url:
                user.avatar_url = sync_data.avatar_url
            user.last_login_at = datetime.now(UTC)
        await self.db.refresh(user)
        return user

    async def _adopt(self, holder: User, sync_data: UserSyncRequest) -> User:
        # Migrate an existing user to the new external_id (auth provider change):
        # email is the stable identifier, external_id can change
        async with self._conflict_savepoint(
            "Email already associated with another account that is signing in concurrently."
        ):
            holder.external_id = sync_data.external_id
            holder.email_verified = True
            holder.display_name = sync_data.display_name
            if sync_data.avatar_url:
                holder.avatar_url = sync_data.avatar_url
            holder.last_login_at = datetime.now(UTC)
        await self.db.refresh(holder)
        return holder

    @asynccontextmanager
    async def _conflict_savepoint(self, message: str) -> AsyncIterator[None]:
        # Changes must be made inside the block: begin_nested() flushes pending state before
        # the savepoint opens, and only what flushes inside it is rolled back on a unique
        # violation, which keeps the request's transaction usable for the 409.
        try:
            async with self.db.begin_nested():
                yield
        except IntegrityError as e:
            raise UserEmailConflictError(message) from e

    async def _detach_email(self, holder: User) -> None:
        # Flushed on its own because the unit of work may order the caller's insert or update
        # of the same address ahead of this update, which would trip the unique constraint.
        holder.email = f"{holder.id}@{DETACHED_EMAIL_DOMAIN}"
        holder.email_verified = False
        await self.db.flush()

    async def _insert_synced_user(
        self, sync_data: UserSyncRequest, email_verified: bool, *, reclaim_from: User | None = None
    ) -> User:
        user = User(
            external_id=sync_data.external_id,
            email=sync_data.email,
            email_verified=email_verified,
            display_name=sync_data.display_name,
            avatar_url=sync_data.avatar_url,
            last_login_at=datetime.now(UTC),
        )
        # A savepoint so that a unique violation leaves the request's transaction usable and
        # undoes the detach along with the insert.
        async with self.db.begin_nested():
            if reclaim_from is not None:
                await self._detach_email(reclaim_from)
            self.db.add(user)
            await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update_last_login(self, user: User) -> None:
        user.last_login_at = datetime.now(UTC)
        await self.db.flush()

    async def complete_onboarding(self, user: User) -> None:
        user.onboarding_completed = True
        await self.db.flush()


class UserEmailConflictError(Exception):
    pass
