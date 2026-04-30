import os
import unittest
from unittest.mock import patch

from app.config import get_database_url, get_settings


class DatabaseUrlConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.load_dotenv_patcher = patch("app.config.load_dotenv", return_value=None)
        self.load_dotenv_patcher.start()

    def tearDown(self) -> None:
        self.load_dotenv_patcher.stop()

    def test_database_url_defaults_to_local_sqlite_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_database_url(), "sqlite:///./finance_bot.db")

    def test_empty_database_url_defaults_to_local_sqlite(self):
        with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=True):
            self.assertEqual(get_database_url(), "sqlite:///./finance_bot.db")

    def test_railway_postgres_url_is_normalized_for_sqlalchemy(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgres://user:pass@host:5432/db"}, clear=True):
            self.assertEqual(
                get_database_url(),
                "postgresql+psycopg://user:pass@host:5432/db",
            )

    def test_postgresql_url_is_normalized_for_psycopg(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@host:5432/db"}, clear=True):
            self.assertEqual(
                get_database_url(),
                "postgresql+psycopg://user:pass@host:5432/db",
            )

    def test_admin_telegram_ids_are_parsed(self):
        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "test-token", "ADMIN_TELEGRAM_IDS": "123, 456"},
            clear=True,
        ):
            self.assertEqual(get_settings().admin_telegram_ids, frozenset({123, 456}))


if __name__ == "__main__":
    unittest.main()
