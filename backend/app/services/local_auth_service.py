from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, exists, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import UserIdentity
from app.models.user import User
from app.schemas.email import normalise_email
from app.utils.passwords import hash_password, needs_rehash, verify_password

LOCAL = "local"
# Serialises /setup so that two first-run requests racing each other cannot both find the
# instance empty and create two administrators.
SETUP_LOCK_KEY = 0x77617264  # "ward"


class SetupAlreadyDoneError(Exception):
    pass


class LocalEmailInUseError(Exception):
    pass


class LocalAuthService:
    """Built-in email + password sign-in, with sessions bound to the user's local identity.

    The local identity row (provider 'local', subject = the user's id) is what local tokens are
    minted for. Replacing it gives it a new id, which ends every token bound to the old one.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def setup_required(self) -> bool:
        return not await self.db.scalar(select(exists().where(User.id.is_not(None))))

    async def create_first_admin(
        self, email: str, password: str, display_name: str | None
    ) -> tuple[User, UUID]:
        # Transaction-scoped, so the lock is held until the request's commit makes the admin
        # visible to whoever waits on it next.
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SETUP_LOCK_KEY})
        if not await self.setup_required():
            raise SetupAlreadyDoneError
        return await self.create_user(email, password, display_name, is_admin=True)

    async def create_user(
        self, email: str, password: str, display_name: str | None, *, is_admin: bool = False
    ) -> tuple[User, UUID]:
        if await self.db.scalar(select(exists().where(func.lower(User.email) == email))):
            raise LocalEmailInUseError
        user = User(
            email=email,
            # An administrator vouched for the address by creating the account.
            email_verified=True,
            display_name=display_name or email.split("@")[0],
            password_hash=await hash_password(password),
            is_admin=is_admin,
        )
        self.db.add(user)
        await self.db.flush()
        identity_id = await self._insert_local_identity(user.id)
        return user, identity_id

    async def authenticate(self, email: str, password: str) -> User | None:
        try:
            normalised = normalise_email(email)
        except ValueError:
            normalised = None
        user = None
        if normalised is not None:
            user = await self.db.scalar(select(User).where(func.lower(User.email) == normalised))
        # verify_password hashes against a dummy when there is no stored hash, so an unknown
        # address takes as long as a wrong password.
        stored = user.password_hash if user is not None else None
        if not await verify_password(stored, password):
            return None
        if user is None or not user.is_active:
            return None
        if needs_rehash(user.password_hash):
            user.password_hash = await hash_password(password)
        return user

    async def sign_in(self, user: User) -> UUID:
        await self.db.execute(
            update(User)
            .where(User.id == user.id)
            .values(last_login_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
        await self._lock_user(user.id)
        identity_id = await self.db.scalar(
            select(UserIdentity.id).where(
                UserIdentity.user_id == user.id, UserIdentity.provider == LOCAL
            )
        )
        if identity_id is None:
            identity_id = await self._insert_local_identity(user.id)
        return identity_id

    async def set_password(self, user: User, new_password: str) -> UUID:
        """Store a new password and end every other local session. Returns the new identity id."""
        user.password_hash = await hash_password(new_password)
        await self.db.flush()
        return await self.rotate_local_identity(user.id)

    async def rotate_local_identity(self, user_id: UUID) -> UUID:
        await self._lock_user(user_id)
        await self.db.execute(
            delete(UserIdentity)
            .where(UserIdentity.user_id == user_id, UserIdentity.provider == LOCAL)
            .execution_options(synchronize_session=False)
        )
        return await self._insert_local_identity(user_id)

    async def list_users(self) -> list[User]:
        result = await self.db.execute(select(User).order_by(User.created_at))
        return list(result.scalars())

    async def _lock_user(self, user_id: UUID) -> None:
        # Identity writes to an existing user happen after its row lock, as UserService requires.
        await self.db.execute(select(User.id).where(User.id == user_id).with_for_update())

    async def _insert_local_identity(self, user_id: UUID) -> UUID:
        return await self.db.scalar(
            insert(UserIdentity)
            .values(user_id=user_id, provider=LOCAL, subject=str(user_id))
            .returning(UserIdentity.id)
        )
