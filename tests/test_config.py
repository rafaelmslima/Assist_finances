import os
import unittest
from unittest.mock import patch

from app.config import get_database_url


class DatabaseUrlConfigTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
