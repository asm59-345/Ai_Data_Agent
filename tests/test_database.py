import os
import sys
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.database import DatabaseUtil, get_default_db_config


def test_database_connection():
    db = DatabaseUtil(get_default_db_config())
    assert db.test_connection() is True


def test_database_schema_overview():
    db = DatabaseUtil(get_default_db_config())
    tables = db.get_tables_overview("public")
    table_names = [t["name"] for t in tables]
    
    assert "users" in table_names
    assert "vehicles" in table_names
    assert "rides" in table_names
    assert "payments" in table_names
    assert "ratings" in table_names


def test_database_query_execution():
    db = DatabaseUtil(get_default_db_config())
    res = db.execute_sql("SELECT COUNT(*) FROM public.users;")
    assert "Columns: count" in res
    assert "10000" in res
