import os
import sys
import re

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.llm_pick import pick_llm
from utils.database import DatabaseUtil, get_default_db_config
from Models.schema import AgentSchema, JudgeSchema
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver


def clean_sql_query(raw_sql: str) -> str:
    """Extracts raw executable SQL from potential markdown fences or commentary."""
    cleaned = raw_sql.strip()
    match = re.search(r"```(?:sql)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    return cleaned.strip()


def curate_ques(state: AgentSchema) -> dict: 
    """Clarifies and structures the user question."""
    user_question = state.user_question or (state.messages[-1].content if state.messages else "")
    try:
        llm = pick_llm("low")
        response = llm.invoke(f"Curate and clarify the following database analytics request: {user_question}").content
    except Exception:
        response = user_question

    return {
        "curated_ques": str(response),
        "messages": [HumanMessage(content=str(response))]
    }


def prompt_query_context(state: AgentSchema) -> dict:
    """Fetches schema information and builds the generation prompt context."""
    curated_question = state.curated_ques
    db = DatabaseUtil(get_default_db_config())
    schema_info = db.schema_details("public")

    prompt = f"""You are an expert PostgreSQL analyst agent.
Convert the user's natural language question into an accurate, efficient Postgres SQL query.
Use the database schema provided below.

CRITICAL INSTRUCTIONS:
1. Generate standard Postgres SQL query ONLY. Do not include any explanations, markdown notes, or commentary.
2. Unless user explicitly requests more or fewer records, ALWAYS include 'LIMIT 10'.
3. Only use SELECT queries. Never generate mutating commands (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE).
4. Table names in PostgreSQL public schema: users, vehicles, rides, payments, ratings.

User Question:
{curated_question}

Database Schema Details:
{schema_info}
"""
    return {"prompt_query_context": prompt}


def generate_sql(state: AgentSchema) -> dict:
    """Generates the Postgres SQL query using the selected LLM."""
    prompt = state.prompt_query_context
    llm = pick_llm("medium")
    raw_query = llm.invoke(prompt).content
    cleaned_query = clean_sql_query(str(raw_query))
    return {"generated_sql_query": cleaned_query}


def is_safe_sql(state: AgentSchema) -> dict:
    """Evaluates SQL query safety against destructive operations."""
    sql_query = state.generated_sql_query.upper()

    destructive_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE", "GRANT", "REVOKE"]
    for kw in destructive_keywords:
        if re.search(r'\b' + kw + r'\b', sql_query):
            return {
                "is_safe": "No",
                "comments": f"Security Violation: Destructive command '{kw}' detected. Only read-only queries are permitted."
            }

    try:
        llm = pick_llm("low")
        prompt = f"""You are an SQL Security Auditor.
Determine if the following SQL query is safe (purely read-only SELECT) or unsafe (modifies schema/data).

Query:
{state.generated_sql_query}
"""
        try:
            llm_judge = llm.with_structured_output(JudgeSchema)
            judgement = llm_judge.invoke(prompt)
            if hasattr(judgement, "answer"):
                ans = judgement.answer
                comm = judgement.comments
            elif isinstance(judgement, dict):
                ans = judgement.get("answer", "Yes")
                comm = judgement.get("comments", "Query validated.")
            else:
                ans = "Yes"
                comm = "Validated"
            return {"is_safe": ans if ans in ["Yes", "No"] else "Yes", "comments": str(comm)}
        except Exception:
            return {"is_safe": "Yes", "comments": "Query validated by rule engine."}
    except Exception as e:
        return {"is_safe": "Yes", "comments": f"Validated with fallback: {e}"}


def canceled_sql(state: AgentSchema) -> dict:
    """Handles unsafe or human-rejected queries."""
    comments = state.comments or "Action was not approved."
    if state.approval_status == "rejected":
        final_ans = "The SQL query was rejected by the human operator. Execution was canceled."
    else:
        final_ans = f"The generated SQL query was deemed unsafe to execute. Reason: {comments}. The query will not be executed."
    
    return {
        "final_answer": final_ans,
        "messages": [AIMessage(content=final_ans)]
    }


def execute_sql(state: AgentSchema) -> dict:
    """Executes the approved SQL query against PostgreSQL."""
    if state.approval_status == "rejected":
        return canceled_sql(state)

    sql_query = clean_sql_query(state.generated_sql_query)
    db = DatabaseUtil(get_default_db_config())
    execution_result = db.execute_sql(sql_query)
    return {"sql_query_execution_result": execution_result}


def represent_final_answer(state: AgentSchema) -> dict:
    """Synthesizes execution results into a user-friendly conversational narrative."""
    execution_result = state.sql_query_execution_result
    curated_question = state.curated_ques

    try:
        llm = pick_llm("low")
        prompt = f"""You are an expert Data Analyst.
Present a clear, concise, and professional answer to the user's question based on the SQL query results.
Highlight the primary findings. Format lists or data clearly.

User Question: {curated_question}
SQL Execution Result:
{execution_result}
"""
        response_text = str(llm.invoke(prompt).content)
    except Exception as e:
        response_text = f"Result of execution:\n{execution_result}"

    return {
        "final_answer": response_text,
        "messages": [AIMessage(content=response_text)]
    }


def is_safe_sql_edge(state: AgentSchema) -> str:
    if state.is_safe.lower() == "yes":
        return "execute_sql"
    return "canceled_sql"


# Build Base Graph
builder = StateGraph(AgentSchema)

builder.add_node("curate_ques", curate_ques)
builder.add_node("prompt_query_context", prompt_query_context)
builder.add_node("generate_sql", generate_sql)
builder.add_node("is_safe_sql", is_safe_sql)
builder.add_node("canceled_sql", canceled_sql)
builder.add_node("execute_sql", execute_sql)
builder.add_node("represent_final_answer", represent_final_answer)

builder.add_edge(START, "curate_ques")
builder.add_edge("curate_ques", "prompt_query_context")
builder.add_edge("prompt_query_context", "generate_sql")
builder.add_edge("generate_sql", "is_safe_sql")
builder.add_conditional_edges("is_safe_sql", is_safe_sql_edge, {
    "execute_sql": "execute_sql",
    "canceled_sql": "canceled_sql"
})
builder.add_edge("canceled_sql", END)
builder.add_edge("execute_sql", "represent_final_answer")
builder.add_edge("represent_final_answer", END)

# Persistent checkpointer for Human-in-the-Loop interruptions
sql_checkpointer = MemorySaver()

# Compile with HITL breakpoint right before execute_sql!
sql_analyst_hitl = builder.compile(
    checkpointer=sql_checkpointer,
    interrupt_before=["execute_sql"]
)

sql_analyst = builder.compile()