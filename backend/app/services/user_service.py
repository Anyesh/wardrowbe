from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import Select, delete, exists, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.identity import UserIdentity
from app.models.user import User
from app.schemas.auth import IDENTITY_TOKEN, TokenPayload
from app.schemas.user import UserSyncRequest

# Reserved by RFC 2606, so a detached address can never be delivered to or claimed by a sign-in.
DETACHED_EMAIL_DOMAIN = "detached.invalid"
EMAIL_IN_USE = "Email already in use by another account."
LEGACY = "legacy"
# Any oidc or dev subject equal to a user's external_id signed into that user before identities
# existed, so these providers claim a matching legacy identity without granting anything new.
LEGACY_CLAIMING_PROVIDERS = frozenset({"oidc", "dev"})
CONCURRENT_SIGN_IN = (
    "Email already associated with another account that is signing in concurrently."
)
SIGN_IN_UNIQUE_CONSTRAINTS = frozenset(
    {"users_email_key", "uq_user_identities_provider_subject", "uq_user_identities_user_provider"}
)
SYNC_ATTEMPTS = 5
UNIQUE_VIOLATION = "23505"
UNVERIFIED_EMAIL_IN_USE = (
    "Email already in use by another account. "
    "Sign in with a provider that verifies this address to use it."
)


class _SignIn(NamedTuple):
    user: User
    identity_id: UUID
    is_new: bool


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_token(self, token: TokenPayload) -> User | None:
        if token.sub_type == IDENTITY_TOKEN:
            try:
                user_id, identity_id = UUID(token.sub), UUID(token.iid or "")
            except ValueError:
                return None
            # Bound to the identity row, so replacing or deleting that identity ends the token.
            query = (
                select(User)
                .join(
                    UserIdentity,
                    (UserIdentity.id == identity_id) & (UserIdentity.user_id == User.id),
                )
                .where(User.id == user_id)
            )
        elif token.sub_type is None:
            # Minted before identities existed, with the user's external_id as sub. Accepted
            # only while the frozen external_id still names the user and the user still holds
            # that subject as a legacy, oidc or dev identity, so an adoption that ends it, or
            # the revoke SQL that NULLs external_id, ends these tokens for good.
            query = select(User).where(
                User.external_id == token.sub,
                exists().where(
                    UserIdentity.user_id == User.id,
                    UserIdentity.subject == token.sub,
                    UserIdentity.provider.in_((LEGACY, *LEGACY_CLAIMING_PROVIDERS)),
                ),
            )
        else:
            return None
        return await self._fetch_current(query.options(selectinload(User.preferences)))

    async def get_by_identity(self, provider: str, subject: str) -> User | None:
        return await self._fetch_current(
            select(User)
            .join(UserIdentity, UserIdentity.user_id == User.id)
            .where(UserIdentity.provider == provider, UserIdentity.subject == subject)
        )

    async def get_by_email(self, email: str) -> User | None:
        return await self._fetch_current(select(User).where(User.email == email))

    async def _fetch_current(self, query: Select) -> User | None:
        # populate_existing because a sync attempt that lost a race leaves the row's earlier
        # state in the identity map, and the next attempt must decide on the committed state.
        result = await self.db.execute(query.execution_options(populate_existing=True))
        return result.scalar_one_or_none()

    async def sync_from_oidc(
        self, sync_data: UserSyncRequest, *, provider: str, email_verified: bool
    ) -> tuple[User, UUID, bool]:
        """
        Sign in the identity (provider, sync_data.external_id), creating its user if needed.
        Returns (user, identity_id, is_new_user); tokens are bound to identity_id.

        provider names the authentication path that vouched for the subject, never the
        client-supplied sync_data.provider. email_verified states whether that path vouched for
        sync_data.email, and is recorded on the user whenever its email is set.

        A user holds at most one identity per provider. An oidc or dev subject matching a
        user's legacy identity (its external_id from before identities existed) claims it. An
        unknown identity whose email belongs to an existing account is added to that account
        when both emails are verified, replacing the account's earlier identity of the same
        provider, so signing in through one provider never breaks another provider's sessions.
        A verified caller whose email is held by an unverified account reclaims it instead:
        that account keeps its data and identities under a detached placeholder address. Any
        other email clash, or a sign-in that keeps losing races, raises UserEmailConflictError.
        """
        if sync_data.email.strip().lower().endswith(f"@{DETACHED_EMAIL_DOMAIN}"):
            raise UserEmailConflictError(EMAIL_IN_USE)
        # Every write below only applies to the row state the decision was made on, so a lost
        # attempt means a concurrent sign-in committed a change to this identity's or this
        # email's row; the next attempt re-reads and decides again. Three attempts cover the
        # longest observed chain (insert loses to the first sign-in, reclaim loses to a twin
        # request, then the twin's row is found), and the rest is headroom. Three or more distinct
        # verified identities racing for one email can still exhaust it, and by design they get
        # the retryable CONCURRENT_SIGN_IN conflict rather than an unbounded loop.
        for _ in range(SYNC_ATTEMPTS):
            try:
                signed_in = await self._sync_once(sync_data, provider, email_verified)
            except _RowChanged:
                continue
            return signed_in
        raise UserEmailConflictError(CONCURRENT_SIGN_IN)

    async def _sync_once(
        self, sync_data: UserSyncRequest, provider: str, email_verified: bool
    ) -> _SignIn:
        subject = sync_data.external_id
        user = await self.get_by_identity(provider, subject)
        if user is not None:
            return await self._sign_in_existing(user, sync_data, provider, email_verified)
        if provider in LEGACY_CLAIMING_PROVIDERS:
            user = await self.get_by_identity(LEGACY, subject)
            if user is not None:
                return await self._sign_in_existing(
                    user, sync_data, provider, email_verified, claim=True
                )
        holder = await self.get_by_email(sync_data.email)
        if holder is None:
            return await self._insert_synced_user(sync_data, provider, email_verified)
        if await self._identity_id(holder.id, provider, subject) is not None:
            # The caller's own row, committed by a concurrent first sign-in between the
            # identity lookup and this one: not an adoption.
            return await self._sign_in_existing(holder, sync_data, provider, email_verified)
        if not email_verified:
            raise UserEmailConflictError(UNVERIFIED_EMAIL_IN_USE)
        # Commit order decides a reclaim racing the holder's own verifying sign-in. If the holder
        # verified first, this caller adopts it here. If the reclaim commits first, the holder
        # stays detached and its sync gets EMAIL_IN_USE, because two verified accounts are never
        # merged automatically; an admin resolves that case.
        if holder.email_verified:
            return await self._adopt(holder, sync_data, provider)
        return await self._insert_synced_user(
            sync_data, provider, email_verified, reclaim_from=holder
        )

    async def _sign_in_existing(
        self,
        user: User,
        sync_data: UserSyncRequest,
        provider: str,
        email_verified: bool,
        *,
        claim: bool = False,
    ) -> _SignIn:
        holder = None
        if user.email != sync_data.email:
            holder = await self.get_by_email(sync_data.email)
            if holder is not None and holder.id == user.id:
                # A twin sync of this identity committed the same move after this attempt read
                # the row: retry against the committed row rather than treat it as a clash.
                raise _RowChanged
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
                await self._lock_in_id_order(holder, user)
                await self._detach_email(holder)
            await self._update_unchanged(user, **values)
            identity_id = await self._held_identity(
                user.id, LEGACY if claim else provider, sync_data.external_id
            )
            if claim:
                identity_id = await self._claim_legacy(identity_id, provider)
        await self.db.refresh(user)
        return _SignIn(user, identity_id, False)

    async def _adopt(self, holder: User, sync_data: UserSyncRequest, provider: str) -> _SignIn:
        # Email is the stable identifier here: the caller's identity joins the verified holder,
        # whose identities of other providers keep working.
        values = {"display_name": sync_data.display_name, "last_login_at": datetime.now(UTC)}
        if sync_data.avatar_url:
            values["avatar_url"] = sync_data.avatar_url
        async with self._attempt_savepoint():
            await self._update_unchanged(holder, **values)
            identity_id = await self._replace_identity(holder.id, provider, sync_data.external_id)
            if provider in LEGACY_CLAIMING_PROVIDERS:
                await self._drop_legacy_identity(holder.id)
        await self.db.refresh(holder)
        return _SignIn(holder, identity_id, False)

    # Invariant: every identity write to an existing user happens after that user's row lock
    # (the CAS in _update_unchanged or _lock_in_id_order), and any new sign-in path must keep
    # to it. That is what makes the re-checks below sound and rules out lock cycles between
    # sign-in paths: a statement run after the lock takes a fresh snapshot, which already holds
    # the outcome of any writer the lock waited out.

    async def _identity_id(self, user_id: UUID, provider: str, subject: str) -> UUID | None:
        return await self.db.scalar(
            select(UserIdentity.id).where(
                UserIdentity.user_id == user_id,
                UserIdentity.provider == provider,
                UserIdentity.subject == subject,
            )
        )

    async def _held_identity(self, user_id: UUID, provider: str, subject: str) -> UUID:
        identity_id = await self._identity_id(user_id, provider, subject)
        if identity_id is None:
            raise _RowChanged
        return identity_id

    async def _claim_legacy(self, identity_id: UUID, provider: str) -> UUID:
        claimed = await self.db.scalar(
            update(UserIdentity)
            .where(UserIdentity.id == identity_id, UserIdentity.provider == LEGACY)
            .values(provider=provider)
            .returning(UserIdentity.id)
            .execution_options(synchronize_session=False)
        )
        if claimed is None:
            raise _RowChanged
        return claimed

    async def _replace_identity(self, user_id: UUID, provider: str, subject: str) -> UUID:
        # One subject per provider. The new subject gets a new row id rather than an updated
        # subject, so tokens bound to the replaced identity stop authenticating.
        replaced = (
            await self.db.execute(
                select(UserIdentity.id, UserIdentity.subject).where(
                    UserIdentity.user_id == user_id, UserIdentity.provider == provider
                )
            )
        ).one_or_none()
        if replaced is not None and replaced.subject == subject:
            # A twin request adopted with this subject while this one waited on the user's
            # lock; replacing its row would end the token the twin just issued.
            return replaced.id
        if replaced is not None:
            result = await self.db.execute(
                delete(UserIdentity)
                .where(UserIdentity.id == replaced.id, UserIdentity.subject == replaced.subject)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise _RowChanged
        return await self._insert_identity(user_id, provider, subject)

    async def _insert_identity(self, user_id: UUID, provider: str, subject: str) -> UUID:
        return await self.db.scalar(
            insert(UserIdentity)
            .values(user_id=user_id, provider=provider, subject=subject)
            .returning(UserIdentity.id)
        )

    async def _drop_legacy_identity(self, user_id: UUID) -> None:
        # Gaining an oidc or dev identity ends the legacy one, as overwriting external_id did
        # before identities existed. Most users have none left, so the rowcount is not checked.
        await self.db.execute(
            delete(UserIdentity)
            .where(UserIdentity.user_id == user_id, UserIdentity.provider == LEGACY)
            .execution_options(synchronize_session=False)
        )

    async def _detach_email(self, holder: User) -> None:
        await self._update_unchanged(
            holder, email=f"{holder.id}@{DETACHED_EMAIL_DOMAIN}", email_verified=False
        )

    async def _lock_in_id_order(self, *users: User) -> None:
        # The holder's row must be detached before the caller's row takes its email, so two
        # accounts swapping emails would each lock the other's row first and deadlock. Taking
        # both locks in id order up front makes one wait for the other, whose CAS then fails.
        await self.db.execute(
            select(User.id)
            .where(User.id.in_([user.id for user in users]))
            .order_by(User.id)
            .with_for_update()
        )

    async def _update_unchanged(self, read: User, **values: object) -> None:
        # A compare-and-swap rather than SELECT ... FOR UPDATE: the decision was made on `read`,
        # and Postgres re-evaluates this WHERE against the committed row once any concurrent
        # writer releases it, so a holder that verified its email or moved to another address
        # meanwhile is left alone, without locking every row the sync only reads. An adoption
        # leaves these columns alone, so the identity re-check after this lock detects it, and
        # last_login_at is never matched, so the holder's own sign-ins cannot starve one.
        result = await self.db.execute(
            update(User)
            .where(
                User.id == read.id,
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
        # transaction usable for the next attempt or the 409. Only a unique violation on a
        # column sign-in writes means a concurrent sign-in committed the identity or email after
        # this attempt's reads; any other integrity error is a bug and must not become a 409.
        try:
            async with self.db.begin_nested():
                yield
        except IntegrityError as e:
            if not _lost_sign_in_race(e):
                raise
            raise _RowChanged from e

    async def _insert_synced_user(
        self,
        sync_data: UserSyncRequest,
        provider: str,
        email_verified: bool,
        *,
        reclaim_from: User | None = None,
    ) -> _SignIn:
        user = User(
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
            identity_id = await self._insert_identity(user.id, provider, sync_data.external_id)
        await self.db.refresh(user)
        return _SignIn(user, identity_id, True)

    async def update_last_login(self, user: User) -> None:
        user.last_login_at = datetime.now(UTC)
        await self.db.flush()

    async def complete_onboarding(self, user: User) -> None:
        user.onboarding_completed = True
        await self.db.flush()


def _lost_sign_in_race(error: IntegrityError) -> bool:
    driver_error = getattr(error.orig, "driver_exception", None)
    return (
        getattr(error.orig, "sqlstate", None) == UNIQUE_VIOLATION
        and getattr(driver_error, "constraint_name", None) in SIGN_IN_UNIQUE_CONSTRAINTS
    )


class UserEmailConflictError(Exception):
    pass


class _RowChanged(Exception):
    pass
