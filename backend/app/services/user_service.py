from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.schemas.user import UserSyncRequest

# Reserved by RFC 2606, so a detached address can never be delivered to or claimed by a sign-in.
DETACHED_EMAIL_DOMAIN = "detached.invalid"
EMAIL_IN_USE = "Email already in use by another account."
CONCURRENT_SIGN_IN = (
    "Email already associated with another account that is signing in concurrently."
)
SYNC_ATTEMPTS = 5
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

        return await self._fetch_current(query)

    async def get_by_email(self, email: str) -> User | None:
        return await self._fetch_current(select(User).where(User.email == email))

    async def _fetch_current(self, query: Select) -> User | None:
        # populate_existing because a sync attempt that lost a race leaves the row's earlier
        # state in the identity map, and the next attempt must decide on the committed state.
        result = await self.db.execute(query.execution_options(populate_existing=True))
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
        address. Any other email clash, or a sign-in that keeps losing races, raises
        UserEmailConflictError.
        """
        if sync_data.email.strip().lower().endswith(f"@{DETACHED_EMAIL_DOMAIN}"):
            raise UserEmailConflictError(EMAIL_IN_USE)
        # Every write below only applies to the row state the decision was made on, so a lost
        # attempt means a concurrent sign-in committed a change to this identity's or this
        # email's row; the next attempt re-reads and decides again. Three attempts cover the
        # longest observed chain (insert loses to the first sign-in, reclaim loses to a twin
        # request, then the twin's row is found), and the rest is headroom.
        for _ in range(SYNC_ATTEMPTS):
            try:
                return await self._sync_once(sync_data, email_verified)
            except _RowChanged:
                continue
        raise UserEmailConflictError(CONCURRENT_SIGN_IN)

    async def _sync_once(
        self, sync_data: UserSyncRequest, email_verified: bool
    ) -> tuple[User, bool]:
        user = await self.get_by_external_id(sync_data.external_id)
        if user is not None:
            return await self._sign_in_existing(user, sync_data, email_verified), False
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

        values = {"display_name": sync_data.display_name, "last_login_at": datetime.now(UTC)}
        if sync_data.avatar_url:
            values["avatar_url"] = sync_data.avatar_url
        if user.email != sync_data.email:
            values |= {"email": sync_data.email, "email_verified": email_verified}
        elif email_verified:
            values["email_verified"] = True
        async with self._attempt_savepoint():
            if holder is not None:
                await self._detach_email(holder)
            await self._update_unchanged(user, **values)
        await self.db.refresh(user)
        return user

    async def _adopt(self, holder: User, sync_data: UserSyncRequest) -> User:
        # Migrate an existing user to the new external_id (auth provider change):
        # email is the stable identifier, external_id can change
        values = {
            "external_id": sync_data.external_id,
            "display_name": sync_data.display_name,
            "last_login_at": datetime.now(UTC),
        }
        if sync_data.avatar_url:
            values["avatar_url"] = sync_data.avatar_url
        async with self._attempt_savepoint():
            await self._update_unchanged(holder, **values)
        await self.db.refresh(holder)
        return holder

    async def _detach_email(self, holder: User) -> None:
        await self._update_unchanged(
            holder, email=f"{holder.id}@{DETACHED_EMAIL_DOMAIN}", email_verified=False
        )

    async def _update_unchanged(self, read: User, **values: object) -> None:
        # A compare-and-swap rather than SELECT ... FOR UPDATE: the decision was made on `read`,
        # and Postgres re-evaluates this WHERE against the committed row once any concurrent
        # writer releases it, so a holder that verified its email, moved to another address or
        # was adopted meanwhile is left alone, without locking every row the sync only reads.
        result = await self.db.execute(
            update(User)
            .where(
                User.id == read.id,
                User.external_id == read.external_id,
                User.email == read.email,
                User.email_verified.is_(read.email_verified),
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise _RowChanged

    @asynccontextmanager
    async def _attempt_savepoint(self) -> AsyncIterator[None]:
        # A savepoint so that a lost race undoes this attempt's writes and leaves the request's
        # transaction usable for the next attempt or the 409. A unique violation means a
        # concurrent sign-in committed the identity or email after this attempt's reads.
        try:
            async with self.db.begin_nested():
                yield
        except IntegrityError as e:
            raise _RowChanged from e

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
        async with self._attempt_savepoint():
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


class _RowChanged(Exception):
    pass
