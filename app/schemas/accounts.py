"""Account input contracts; passwords are never normalized or serialized back."""
import unicodedata
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, field_validator


def email_key(value):
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("이메일에 사용할 수 없는 문자가 있습니다.") from None
        return unicodedata.normalize("NFKC", value).strip().casefold()
    return value


EmailKey = Annotated[EmailStr, BeforeValidator(email_key)]


class LoginPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    email: EmailKey
    password: str

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value: str) -> str:
        try:
            length = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            raise ValueError("비밀번호에 사용할 수 없는 문자가 있습니다.") from None
        if not 1 <= length <= 72:
            raise ValueError("비밀번호는 1~72 UTF-8 바이트로 입력해 주세요.")
        return value


class SignupPayload(LoginPayload):
    @field_validator("password")
    @classmethod
    def registration_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("가입 비밀번호는 8자 이상이어야 합니다.")
        return value


class AccountView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
