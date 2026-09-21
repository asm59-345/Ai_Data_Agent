import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.server import app

client = TestClient(app)


def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "database" in data
    assert data["database"]["connected"] is True


def test_api_database_tables():
    res = client.get("/api/database/tables")
    assert res.status_code == 200
    data = res.json()
    assert "tables" in data
    table_names = [t["name"] for t in data["tables"]]
    assert "users" in table_names
    assert "rides" in table_names


def test_api_chat_hitl_cycle():
    mock_resp = MagicMock()
    mock_resp.content = "SELECT payment_method, COUNT(*) FROM public.payments GROUP BY payment_method LIMIT 5;"

    with patch("agents.sql_analyst.pick_llm") as mock_pick:
        mock_inst = MagicMock()
        mock_inst.invoke.return_value = mock_resp
        mock_pick.return_value = mock_inst

        # 1. Send query triggering HITL
        chat_res = client.post("/api/chat", json={
            "message": "What are the top payment methods?"
        })
        assert chat_res.status_code == 200
        chat_data = chat_res.json()
        assert chat_data["status"] == "pending_approval"
        assert chat_data["requires_approval"] is True
        assert "payments" in chat_data["generated_sql_query"]

        thread_id = chat_data["thread_id"]

        # 2. Approve query
        approve_res = client.post(f"/api/runs/{thread_id}/approve", json={
            "action": "approve"
        })
        assert approve_res.status_code == 200
        approve_data = approve_res.json()
        assert approve_data["status"] == "completed"
        assert "sql_query_execution_result" in approve_data
