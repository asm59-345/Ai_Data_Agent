import os
import sys
import uuid
import pytest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.sql_analyst import sql_analyst_hitl
from Models.schema import AgentSchema


def test_sql_analyst_hitl_breakpoint_and_resume():
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    mock_llm_response = MagicMock()
    mock_llm_response.content = "SELECT COUNT(*) FROM public.vehicles;"

    with patch("agents.sql_analyst.pick_llm") as mock_pick_llm:
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_llm_response
        mock_pick_llm.return_value = mock_instance

        state_input = AgentSchema(user_question="Count total number of vehicles")

        # 1. Initial invocation halts right before execute_sql breakpoint
        sql_analyst_hitl.invoke(state_input, config)
        snapshot = sql_analyst_hitl.get_state(config)

        assert snapshot.next is not None
        assert "execute_sql" in snapshot.next
        assert "vehicles" in snapshot.values["generated_sql_query"]
        assert snapshot.values["is_safe"] == "Yes"

        # 2. Simulate Human Operator approval & resume
        sql_analyst_hitl.update_state(config, {"approval_status": "approved"}, as_node="is_safe_sql")
        sql_analyst_hitl.invoke(None, config)

        resumed_snapshot = sql_analyst_hitl.get_state(config)
        assert resumed_snapshot.next == ()
        assert "3000" in resumed_snapshot.values["sql_query_execution_result"]
