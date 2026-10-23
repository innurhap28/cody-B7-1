"""Account transactions; HTTP/session policy stays in the route layer."""
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.errors import APIError
from app.models.user import User
from app.schemas.accounts import LoginPayload, SignupPayload
from app.security import hash_password, is_legacy_hash, verify_password

log = logging.getLogger(__name__)
_DUMMY_HASH = hash_password("shortform-unregistered-account")


class AccountService:
    def __init__(self, db: Session):
        self.db = db

    def register(self, payload: SignupPayload) -> User:
        account = User(email=str(payload.email), password_hash=hash_password(payload.password))
        self.db.add(account)
        try:
            self.db.commit()
            self.db.refresh(account)
        except IntegrityError:
            self.db.rollback()
            raise APIError(409, "EMAIL_TAKEN", "이미 가입된 이메일입니다.") from None
        except SQLAlchemyError:
            self.db.rollback()
            log.error("db_save_fail operation=account_create")
            raise APIError(503, "DB_ERROR", "가입 정보를 저장하지 못했습니다.") from None
        log.info("db_save_success operation=account_create user_id=%s", account.id)
        return account

    def authenticate(self, payload: LoginPayload) -> User:
        account = self.db.scalar(select(User).filter_by(email=str(payload.email)))
        valid = verify_password(payload.password, account.password_hash if account else _DUMMY_HASH)
        if not account or not valid:
            log.warning("login_rejected")
            raise APIError(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호를 확인해 주세요.")
        if is_legacy_hash(account.password_hash):
            account.password_hash = hash_password(payload.password)
            try:
                self.db.commit()
            except SQLAlchemyError:
                self.db.rollback()
                log.error("db_save_fail operation=credential_upgrade user_id=%s", account.id)
                raise APIError(503, "DB_ERROR", "인증 정보를 갱신하지 못했습니다.") from None
            log.info("db_save_success operation=credential_upgrade user_id=%s", account.id)
        return account
