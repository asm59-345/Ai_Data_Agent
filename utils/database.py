import os
import psycopg2
from psycopg2 import sql, extras
from typing import Dict, Any, List, Optional


class DatabaseUtil:
    """
    Robust PostgreSQL utility for schema inspection and query execution.
    Manages connections safely without closing the shared instance connection prematurely.
    """

    def __init__(self, db_config: Dict[str, Any]):
        self.db_config = db_config
        self.connection = None
        self._connect()

    def _connect(self):
        """Establishes or re-establishes the database connection."""
        try:
            if self.connection is None or self.connection.closed:
                # Ensure port is integer
                config = dict(self.db_config)
                if "port" in config:
                    config["port"] = int(config["port"])
                self.connection = psycopg2.connect(**config)
        except Exception as e:
            print(f"[DatabaseUtil] Connection error: {e}")
            self.connection = None

    def test_connection(self) -> bool:
        """Tests if the database connection is currently alive."""
        try:
            self._connect()
            if not self.connection or self.connection.closed:
                return False
            with self.connection.cursor() as cur:
                cur.execute("SELECT 1;")
                return cur.fetchone()[0] == 1
        except Exception:
            return False

    def schema_details(self, schema_name: str = "public") -> str:
        """
        Extracts comprehensive schema metadata including tables, column types,
        primary/foreign keys, and sample data.
        """
        self._connect()
        if not self.connection or self.connection.closed:
            return f"Error: Unable to connect to database using provided credentials."

        schema_info_context = f"Database Schema: {schema_name}\n"

        try:
            with self.connection.cursor() as cursor:
                # 1. Fetch tables in the given schema
                cursor.execute(
                    """
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = %s 
                      AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                    """,
                    (schema_name,)
                )
                tables = [row[0] for row in cursor.fetchall()]

                if not tables:
                    return f"Schema '{schema_name}' has no user tables or is empty."

                for table_name in tables:
                    schema_info_context += f"\nTable: {table_name}\n"

                    # 2. Fetch columns and data types
                    cursor.execute(
                        """
                        SELECT column_name, data_type, is_nullable
                        FROM information_schema.columns 
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position;
                        """,
                        (schema_name, table_name)
                    )
                    columns = cursor.fetchall()
                    for col_name, data_type, is_null in columns:
                        nullable_str = " (nullable)" if is_null == "YES" else " (not null)"
                        schema_info_context += f"  Column: {col_name}, Type: {data_type}{nullable_str}\n"

                    # 3. Fetch safe sample data (up to 3 rows)
                    sample_query = sql.SQL("SELECT * FROM {}.{} LIMIT 3;").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(table_name)
                    )
                    try:
                        cursor.execute(sample_query)
                        sample_rows = cursor.fetchall()
                        if sample_rows:
                            schema_info_context += "  Sample Data (First 3 rows):\n"
                            for row in sample_rows:
                                schema_info_context += f"    {row}\n"
                        else:
                            schema_info_context += "  Sample Data: (Table is empty)\n"
                    except Exception as sample_err:
                        schema_info_context += f"  Sample Data: Unavailable ({sample_err})\n"

        except Exception as e:
            return f"Error fetching schema details: {e}"

        return schema_info_context

    def get_tables_overview(self, schema_name: str = "public") -> List[Dict[str, Any]]:
        """Returns structured metadata for all tables in the schema."""
        self._connect()
        if not self.connection or self.connection.closed:
            return []

        overview = []
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = %s AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                    """,
                    (schema_name,)
                )
                tables = [row[0] for row in cursor.fetchall()]

                for table in tables:
                    # Count rows
                    count_q = sql.SQL("SELECT COUNT(*) FROM {}.{};").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(table)
                    )
                    cursor.execute(count_q)
                    row_count = cursor.fetchone()[0]

                    # Columns
                    cursor.execute(
                        """
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position;
                        """,
                        (schema_name, table)
                    )
                    columns = [{"name": c[0], "type": c[1]} for c in cursor.fetchall()]

                    overview.append({
                        "name": table,
                        "row_count": row_count,
                        "columns": columns
                    })
        except Exception as e:
            print(f"[DatabaseUtil] Failed to get table overview: {e}")

        return overview

    def execute_sql(self, query: str) -> str:
        """
        Executes a validated read-only SQL query and returns formatted tabular results.
        """
        self._connect()
        if not self.connection or self.connection.closed:
            return "Error: Database connection is not available."

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                if cursor.description:
                    col_names = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    self.connection.commit()
                    
                    if not rows:
                        return "Query executed successfully. Result set is empty (0 rows returned)."
                    
                    # Format tabular output
                    formatted = [f"Columns: {', '.join(col_names)}", f"Total Rows: {len(rows)}", "Results:"]
                    for idx, row in enumerate(rows, 1):
                        formatted.append(f"Row {idx}: {row}")
                    return "\n".join(formatted)
                else:
                    self.connection.commit()
                    return "Query executed successfully (no result rows)."
        except Exception as e:
            if self.connection and not self.connection.closed:
                self.connection.rollback()
            return f"Database Error during execution: {e}"

    def close(self):
        """Explicitly closes the database connection."""
        if self.connection and not self.connection.closed:
            self.connection.close()


def get_default_db_config() -> Dict[str, Any]:
    """Helper to load db credentials from environment variables with safe fallbacks."""
    # Prioritize user from env, fallback to 'postgres' if agentdb fails
    return {
        "host": os.environ.get("host", "localhost"),
        "port": int(os.environ.get("port", 5432)),
        "user": os.environ.get("user", "postgres"),
        "password": os.environ.get("password", "8521"),
        "dbname": os.environ.get("database", "postgres"),
    }