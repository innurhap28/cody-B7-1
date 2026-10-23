"""Credential storage and compatibility with the previous local SQLite schema."""
import os
from pathlib import Path
import tempfile
import unittest

import bcrypt
from sqlalchemy import text
from sqlalchemy.orm import Session

os.environ.setdefault("SECRET_KEY", "test-only-shortform-at-least-32-chars")
from app.database import create_db_engine
from app.schemas.accounts import LoginPayload
from app.security import hash_password, verify_password
from app.services.accounts import AccountService


class CredentialTests(unittest.TestCase):
    def test_hash_uses_unique_salts_and_rejects_wrong_password(self):
        left = hash_password("Independent-shortform-1234")
        right = hash_password("Independent-shortform-1234")
        self.assertNotEqual(left, right)
        self.assertTrue(verify_password("Independent-shortform-1234", left))
        self.assertFalse(verify_password("incorrect-password", left))
        self.assertNotIn("Independent", left)

    def test_corrupt_or_unbounded_hash_parameters_are_rejected(self):
        samples = [None, "", "scrypt$1073741824$8$1$xx$xx", "scrypt$16384$8$1$!!!!$!!!!", "$2b$broken"]
        for value in samples:
            with self.subTest(value=value):
                self.assertFalse(verify_password("Shortform-password-1234", value))

    def test_password_unicode_byte_limit_and_invalid_unicode(self):
        encoded = hash_password("가" * 24)
        self.assertTrue(verify_password("가" * 24, encoded))
        self.assertFalse(verify_password("가" * 25, encoded))
        self.assertFalse(verify_password("\ud800", encoded))
        with self.assertRaises(ValueError):
            hash_password("가" * 25)

    def test_old_varchar60_sqlite_rows_upgrade_without_schema_or_id_changes(self):
        password = "Legacy-password-1234"
        with tempfile.TemporaryDirectory(dir=os.environ.get("SHORTFORM_TEST_TMPDIR")) as folder:
            engine = create_db_engine("sqlite:///" + str(Path(folder) / "legacy.db"))
            try:
                with engine.begin() as connection:
                    connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email VARCHAR(255) UNIQUE NOT NULL, password_hash VARCHAR(60) NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"))
                    connection.execute(text("INSERT INTO users (id, email, password_hash) VALUES (17, :email, :password_hash)"),
                                       {"email": "legacy@example.com", "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()})
                with Session(engine) as db:
                    account = AccountService(db).authenticate(LoginPayload(email="legacy@example.com", password=password))
                    self.assertEqual(account.id, 17)
                    self.assertTrue(account.password_hash.startswith("scrypt$"))
                    self.assertGreater(len(account.password_hash), 60)
                    self.assertTrue(verify_password(password, account.password_hash))
            finally:
                engine.dispose()
