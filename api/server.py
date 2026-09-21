import os
import sys
import uuid
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.database import DatabaseUtil, get_default_db_config
from utils.llm_pick import pick_llm
from Models.schema import AgentSchema, DataAgentSchema
from agents.sql_analyst import sql_analyst_hitl, sql_analyst
from agents.etl_analyst import etl_analyst
from agents.data_agent import data_agent

app = FastAPI(
    title="AI Data Agent API",
    description="Agentic Data Intelligence Platform with LangGraph Human-in-the-Loop approval gate.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory thread storage for active runs
ACTIVE_THREADS: Dict[str, Dict[str, Any]] = {}


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    force_route: Optional[str] = None  # 'sql', 'etl', or auto


class ApprovalRequest(BaseModel):
    action: str  # 'approve', 'modify', 'reject'
    modified_query: Optional[str] = None
    feedback: Optional[str] = None


@app.get("/api/health")
def get_health():
    """Returns connection health for DB and LLM configuration."""
    db = DatabaseUtil(get_default_db_config())
    db_connected = db.test_connection()
    
    openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))
    gemini = bool(os.environ.get("GEMINI_API_KEY"))
    openai = bool(os.environ.get("OPENAI_API_KEY"))
    anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))

    active_provider = "Unknown"
    if gemini:
        active_provider = "Google Gemini (gemini-flash-latest)"
    elif openai:
        active_provider = "OpenAI"
    elif anthropic:
        active_provider = "Anthropic"
    elif openrouter:
        active_provider = "OpenRouter"
    elif openai:
        active_provider = "OpenAI"
    elif anthropic:
        active_provider = "Anthropic"

    return {
        "status": "healthy" if db_connected else "degraded",
        "database": {
            "connected": db_connected,
            "host": os.environ.get("host", "localhost"),
            "port": os.environ.get("port", 5432),
            "dbname": os.environ.get("database", "postgres"),
            "user": os.environ.get("user", "postgres"),
        },
        "llm": {
            "active_provider": active_provider,
            "openrouter_configured": openrouter,
            "gemini_configured": gemini,
            "openai_configured": openai,
            "anthropic_configured": anthropic,
        }
    }


@app.get("/api/database/tables")
def get_database_tables():
    """Inspects PostgreSQL schema and returns all table definitions with row counts."""
    db = DatabaseUtil(get_default_db_config())
    tables = db.get_tables_overview("public")
    return {"tables": tables}


@app.post("/api/database/seed")
def seed_database():
    """Executes database seeding using feed_db.py."""
    import subprocess
    feed_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "feed_db.py"))
    result = subprocess.run([sys.executable, feed_script], capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Database seed failed: {result.stderr}")
    return {"message": "Database successfully seeded.", "output": result.stdout}


@app.post("/api/chat")
def handle_chat(req: ChatRequest):
    """
    Processes incoming natural language queries.
    Uses LangGraph Human-in-the-Loop breakpoint prior to SQL execution.
    """
    thread_id = req.thread_id or str(uuid.uuid4())
    message = req.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Determine route: if explicitly forced or check ETL keywords
    route = req.force_route
    if not route:
        lower_msg = message.lower()
        if any(w in lower_msg for w in ["http://", "https://", "extract", "pokeapi", "parquet", "transform"]):
            route = "etl"
        else:
            route = "sql"

    config = {"configurable": {"thread_id": thread_id}}

    if route == "etl":
        # Run ETL Analyst
        try:
            from langchain_core.messages import HumanMessage
            response = etl_analyst.invoke({"messages": [HumanMessage(content=message)]})
            last_message = response["messages"][-1].content
            return {
                "thread_id": thread_id,
                "status": "completed",
                "route": "etl",
                "final_answer": last_message,
                "requires_approval": False
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"ETL execution error: {e}")

    # Route: SQL Analyst with Human-in-the-Loop breakpoint
    state_input = AgentSchema(user_question=message)
    
    # Run the graph up to the breakpoint (interrupt_before=["execute_sql"])
    try:
        # Initial invocation pauses at interrupt_before
        sql_analyst_hitl.invoke(state_input, config)
        snapshot = sql_analyst_hitl.get_state(config)
        
        # Check if paused at execute_sql breakpoint
        if snapshot.next and "execute_sql" in snapshot.next:
            values = snapshot.values
            ACTIVE_THREADS[thread_id] = {
                "route": "sql",
                "question": message,
                "config": config,
            }
            return {
                "thread_id": thread_id,
                "status": "pending_approval",
                "route": "sql",
                "requires_approval": True,
                "curated_question": values.get("curated_ques", message),
                "generated_sql_query": values.get("generated_sql_query", ""),
                "is_safe": values.get("is_safe", "Yes"),
                "comments": values.get("comments", "Query ready for execution."),
                "next_step": "execute_sql"
            }
        else:
            # Query was flagged unsafe or finished directly
            values = snapshot.values
            return {
                "thread_id": thread_id,
                "status": "completed",
                "route": "sql",
                "requires_approval": False,
                "curated_question": values.get("curated_ques", message),
                "generated_sql_query": values.get("generated_sql_query", ""),
                "is_safe": values.get("is_safe", "No"),
                "comments": values.get("comments", ""),
                "final_answer": values.get("final_answer", "Query execution stopped."),
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL analyst error: {e}")


@app.post("/api/runs/{thread_id}/approve")
def handle_approval(thread_id: str, req: ApprovalRequest):
    """
    Resumes a paused thread after human review:
    - 'approve': Runs the generated query.
    - 'modify': Updates query with operator edits and runs it.
    - 'reject': Cancels execution.
    """
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = sql_analyst_hitl.get_state(config)

    if not snapshot.values:
        raise HTTPException(status_code=404, detail="Active run thread not found or expired.")

    action = req.action.lower().strip()

    if action == "reject":
        # Update state to rejected and run canceled node
        sql_analyst_hitl.update_state(
            config,
            {"approval_status": "rejected", "user_feedback": req.feedback or "Rejected by operator."},
            as_node="is_safe_sql"
        )
        # Finalize
        return {
            "thread_id": thread_id,
            "status": "rejected",
            "final_answer": "Query execution was canceled by the human operator.",
            "sql_query_execution_result": "None (Canceled)",
        }

    # Action: approve or modify
    updates = {"approval_status": "approved"}
    if action == "modify" and req.modified_query:
        updates["generated_sql_query"] = req.modified_query.strip()
        updates["approval_status"] = "modified"

    sql_analyst_hitl.update_state(config, updates, as_node="is_safe_sql")

    # Resume graph execution (None as input resumes from current checkpoint)
    try:
        res = sql_analyst_hitl.invoke(None, config)
        final_state = sql_analyst_hitl.get_state(config).values

        return {
            "thread_id": thread_id,
            "status": "completed",
            "final_answer": final_state.get("final_answer", ""),
            "generated_sql_query": final_state.get("generated_sql_query", ""),
            "sql_query_execution_result": final_state.get("sql_query_execution_result", ""),
            "approval_status": final_state.get("approval_status", "approved"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resumed execution failed: {e}")


# Static files mount
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=FileResponse)
def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse("<h1>AI Data Agent</h1><p>Frontend static file loading...</p>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
