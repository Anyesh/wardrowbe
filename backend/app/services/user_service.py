from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import Select, delete, exists, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.models.identity import UserIdentity
from app.models.user import User
from app.schemas.auth import IDENTITY_TOKEN, TokenPayload
from app.schemas.email import normalise_email
from app.schemas.user import UserSyncRequest

# Reserved by RFC 2606, so a detached address can never be delivered to or claimed by a sign-in.
DETACHED_EMAIL_DOMAIN = "detached.invalid"
EMAIL_IN_USE = "Email already in use by another account."
FORWARD_AUTH = "forward_auth"
LEGACY = "legacy"
LEGACY_IDENTITY_CONFLICT = "legacy_identity_conflict"
# Forward-auth before identities gave a user the proxy sent no Remote-Email for
# "<Remote-User>@forward-auth.local" (frontend sign-in) or "<Remote-User>@example.com" (backend
# header check).
PRE_IDENTITY_PROXY_EMAIL_DOMAINS = ("forward-auth.local", "example.com")
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


class _LegacyHolder(NamedTuple):
    user: User
    subject: str
    holds_proxy_identity: bool
    caller_identity_exists: bool


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

    async def holds_identity(self, user_id: UUID, provider: str, subject: str) -> bool:
        return await self._identity_id(user_id, provider, subject) is not None

    async def _legacy_holder_of_proxy_user(self, subject: str) -> _LegacyHolder | None:
        # Forward-auth before identities stored Remote-User as Starlette and Node read it, as
        # Latin-1, so a non-ASCII username's legacy row holds its UTF-8 bytes as Latin-1.
        latin1 = subject.encode("utf-8").decode("latin-1")
        legacy = aliased(UserIdentity)
        for legacy_subject in dict.fromkeys((subject, latin1)):
            if _read_as_latin1(legacy_subject) not in (None, subject):
                # That row is the Latin-1 spelling of another username, so it is that user's.
                continue
            # One statement, so the holder's email, whether it has a forward_auth identity and
            # whether the caller's own identity exists by now come from the same snapshot: a
            # twin's sign-in changes them together, and a conflict decided on a mix of old and
            # new values would refuse the twin.
            row = (
                await self.db.execute(
                    select(
                        User,
                        exists().where(
                            UserIdentity.user_id == User.id, UserIdentity.provider == FORWARD_AUTH
                        ),
                        exists().where(
                            UserIdentity.provider == FORWARD_AUTH, UserIdentity.subject == subject
                        ),
                    )
                    .join(legacy, legacy.user_id == User.id)
                    .where(legacy.provider == LEGACY, legacy.subject == legacy_subject)
                    .execution_options(populate_existing=True)
                )
            ).one_or_none()
            if row is not None:
                return _LegacyHolder(row[0], legacy_subject, row[1], row[2])
        return None

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
        user's legacy identity (its external_id from before identities existed) claims it. A
        forward_auth subject is a proxy username that may only coincide with a legacy subject,
        so it claims a verified legacy holder only when that holder's email is the proxy's or a
        placeholder forward-auth gave users before identities, and the holder has no
        forward_auth identity yet; the legacy row stays for its other owner. An
        unverified legacy holder is ignored, and any other verified one raises
        UserEmailConflictError(LEGACY_IDENTITY_CONFLICT) unless it already holds a forward_auth
        identity and the proxy's exact email, which the email rules below then decide. An
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
        expected_holder_id = None
        if provider in LEGACY_CLAIMING_PROVIDERS:
            user = await self.get_by_identity(LEGACY, subject)
            if user is not None:
                return await self._sign_in_existing(
                    user, sync_data, provider, email_verified, legacy_subject=subject
                )
        elif provider == FORWARD_AUTH:
            legacy = await self._legacy_holder_of_proxy_user(subject)
            if legacy is not None and legacy.caller_identity_exists:
                # Committed since the identity lookup above, which the retry repeats.
                raise _RowChanged
            # An unverified holder may be a squatter on the owner's address, so the email rules
            # below decide, and may reclaim the address, rather than its legacy row.
            if legacy is not None and legacy.user.email_verified:
                if not legacy.holds_proxy_identity and _is_proxy_users_email(
                    legacy.user.email, sync_data.email, legacy.subject
                ):
                    return await self._sign_in_existing(
                        legacy.user,
                        sync_data,
                        provider,
                        email_verified,
                        legacy_subject=legacy.subject,
                    )
                if not (legacy.holds_proxy_identity and legacy.user.email == sync_data.email):
                    raise UserEmailConflictError(LEGACY_IDENTITY_CONFLICT)
                expected_holder_id = legacy.user.id
        holder = await self.get_by_email(sync_data.email)
        if expected_holder_id is not None and (holder is None or holder.id != expected_holder_id):
            # Retried because the decision above relied on the legacy holder keeping the proxy
            # email, and it moved off it after that read.
            raise _RowChanged
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
        legacy_subject: str | None = None,
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
            if legacy_subject is None:
                identity_id = await self._held_identity(user.id, provider, sync_data.external_id)
            else:
                legacy_id = await self._held_identity(user.id, LEGACY, legacy_subject)
                identity_id = await self._claim_legacy(
                    user.id, legacy_id, provider, sync_data.external_id
                )
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

    async def _claim_legacy(
        self, user_id: UUID, identity_id: UUID, provider: str, subject: str
    ) -> UUID:
        if provider == FORWARD_AUTH:
            # The legacy row stays, because the subject may also be the account's pre-upgrade
            # OIDC subject: that sign-in can still claim it, and pre-upgrade tokens keep working.
            # A forward_auth identity gained meanwhile fails uq_user_identities_user_provider,
            # and the retry decides again.
            return await self._insert_identity(user_id, provider, subject)
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


def _is_proxy_users_email(email: str, proxy_email: str, legacy_subject: str) -> bool:
    # Stored addresses were kept as sent, so the stored side is normalised too.
    stored = _normalised(email)
    placeholders = {
        _normalised(f"{legacy_subject}@{domain}") for domain in PRE_IDENTITY_PROXY_EMAIL_DOMAINS
    }
    return stored == proxy_email or stored in placeholders


def _read_as_latin1(subject: str) -> str | None:
    try:
        return subject.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return None


def _normalised(email: str) -> str:
    # A Latin-1 read CJK username holds C1 control characters that normalisation refuses,
    # and such an address can still equal its own placeholder.
    try:
        return normalise_email(email)
    except ValueError:
        return email.strip().lower()


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
