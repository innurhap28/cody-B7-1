"""Resolve signed session identities before accessing owner-scoped resources."""
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import APIError
from app.models.user import User


def get_current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User | None:
    identity = request.session.get("user_id")
    if type(identity) is not int or identity < 1:
        request.session.clear()
        return None
    account = db.get(User, identity)
    if account is None:
        request.session.clear()
    return account


def require_login(account: Annotated[User | None, Depends(get_current_user)]) -> User:
    if account is None:
        raise APIError(401, "LOGIN_REQUIRED", "로그인 후 이용해 주세요.")
    return account
