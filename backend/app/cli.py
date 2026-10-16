"""Account administration from inside the container, for when nobody can sign in yet.

    docker compose exec backend python -m app.cli create-user you@example.com --admin
    docker compose exec backend python -m app.cli set-password you@example.com
    docker compose exec backend python -m app.cli list-users

The password is read from the terminal (or from stdin with --password-stdin) so that it never
lands in the shell history or the process list.
"""

import argparse
import asyncio
import getpass
import sys

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select

from app.database import async_session_maker, engine
from app.models.user import User
from app.schemas.email import EmailAddress
from app.schemas.local_auth import NewPassword
from app.services.local_auth_service import LocalAuthService, LocalEmailInUseError


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("New password: ")
        if getpass.getpass("Repeat password: ") != password:
            raise SystemExit("Passwords do not match.")
    try:
        return TypeAdapter(NewPassword).validate_python(password)
    except ValidationError as e:
        raise SystemExit(f"Invalid password: {e.errors()[0]['msg']}") from None


def _email(value: str) -> str:
    try:
        return TypeAdapter(EmailAddress).validate_python(value)
    except ValidationError:
        raise SystemExit(f"{value!r} is not a valid email address.") from None


async def _set_password(email: str, from_stdin: bool, make_admin: bool) -> None:
    password = _read_password(from_stdin)
    async with async_session_maker() as db:
        user = await db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            raise SystemExit(f"No account uses {email}. Use create-user instead.")
        await LocalAuthService(db).set_password(user, password)
        if make_admin:
            user.is_admin = True
        await db.commit()
    print(f"Password set for {email}. Other sessions of this account were signed out.")


async def _create_user(email: str, name: str | None, from_stdin: bool, make_admin: bool) -> None:
    password = _read_password(from_stdin)
    async with async_session_maker() as db:
        try:
            await LocalAuthService(db).create_user(email, password, name, is_admin=make_admin)
        except LocalEmailInUseError:
            raise SystemExit(f"{email} already has an account. Use set-password.") from None
        await db.commit()
    print(f"Created {'administrator' if make_admin else 'account'} {email}.")


async def _list_users() -> None:
    async with async_session_maker() as db:
        users = (await db.execute(select(User).order_by(User.created_at))).scalars()
        for user in users:
            flags = [
                "admin" if user.is_admin else "",
                "password" if user.password_hash else "no-password",
                "" if user.is_active else "inactive",
            ]
            print(f"{user.email}\t{user.display_name}\t{' '.join(f for f in flags if f)}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    set_password = commands.add_parser("set-password", help="set an existing account's password")
    set_password.add_argument("email")
    set_password.add_argument("--admin", action="store_true", help="also make it administrator")
    set_password.add_argument("--password-stdin", action="store_true")

    create = commands.add_parser("create-user", help="create an account with a password")
    create.add_argument("email")
    create.add_argument("--name", help="display name (defaults to the email's local part)")
    create.add_argument("--admin", action="store_true", help="make it an administrator")
    create.add_argument("--password-stdin", action="store_true")

    commands.add_parser("list-users", help="list accounts")

    args = parser.parse_args(argv)

    async def run() -> None:
        try:
            if args.command == "set-password":
                await _set_password(_email(args.email), args.password_stdin, args.admin)
            elif args.command == "create-user":
                await _create_user(_email(args.email), args.name, args.password_stdin, args.admin)
            else:
                await _list_users()
        finally:
            await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
