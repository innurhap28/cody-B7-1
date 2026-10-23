"""Account endpoints: validate -> account service -> signed session."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_login
from app.models.user import User
from app.schemas.accounts import AccountView, LoginPayload, SignupPayload
from app.services.accounts import AccountService

router = APIRouter(prefix="/api/auth", tags=["accounts"])
log = logging.getLogger(__name__)
Database = Annotated[Session, Depends(get_db)]
SignedIn = Annotated[User, Depends(require_login)]


@router.post("/signup", status_code=201, response_model=AccountView)
def create_account(payload: SignupPayload, db: Database):
    return AccountService(db).register(payload)


@router.post("/login", response_model=AccountView)
def start_session(payload: LoginPayload, request: Request, db: Database):
    account = AccountService(db).authenticate(payload)
    request.session.clear()
    request.session.update(user_id=account.id)
    log.info("session_started user_id=%s", account.id)
    return account


@router.post("/logout", status_code=204)
def end_session(request: Request, account: SignedIn):
    request.session.clear()
    log.info("session_ended user_id=%s", account.id)
    return Response(status_code=204)
