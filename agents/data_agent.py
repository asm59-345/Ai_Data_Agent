import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.llm_pick import pick_llm
from Models.schema import RouterSchema, DataAgentSchema, AgentSchema
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from agents.sql_analyst import sql_analyst
from agents.etl_analyst import etl_analyst


def router_node(state: DataAgentSchema):
    """Classifies user query intent as either SQL database query or ETL workflow."""
    message = state.messages[-1].content if state.messages else ""
    llm = pick_llm("low")

    prompt = f"""You are a master Data Agent Router.
Determine whether the user query requires querying an existing relational PostgreSQL database ('sql')
OR performing an ETL operation like extracting data from a REST API endpoint or transforming local files with Python/Pandas ('etl').

User Query: "{message}"

Guidelines:
- Database analysis, statistics, counts, table queries, schema queries -> 'sql'
- API extraction, fetching web endpoints, transforming CSV/JSON/Parquet files -> 'etl'

Respond in structured JSON format with "answer" ('sql' or 'etl') and "comments".
"""
    try:
        llm_router = llm.with_structured_output(RouterSchema)
        route_result = llm_router.invoke(prompt).model_dump()
        route = route_result.get("answer", "sql")
    except Exception:
        # Fallback heuristic router if structured output is unavailable
        lower_msg = message.lower()
        if any(w in lower_msg for w in ["http://", "https://", "api", "extract", "pokeapi", "transform", "csv to", "parquet"]):
            route = "etl"
        else:
            route = "sql"

    return {"route_response": route}


def etl_node(state: DataAgentSchema):
    """Executes the ETL sub-agent."""
    message = state.messages[-1].content if state.messages else ""
    response = etl_analyst.invoke({"messages": [HumanMessage(content=message)]})
    last_msg = response["messages"][-1]
    return {"messages": [last_msg]}


def sql_node(state: DataAgentSchema):
    """Executes the SQL Analyst sub-agent."""
    message = state.messages[-1].content if state.messages else ""
    input_schema = AgentSchema(user_question=message)
    response = sql_analyst.invoke(input_schema)
    final_text = response.final_answer or (response.messages[-1].content if response.messages else "")
    return {"messages": [AIMessage(content=final_text)]}


def route_edge(state: DataAgentSchema) -> str:
    if state.route_response == "etl":
        return "etl_node"
    return "sql_node"


builder = StateGraph(DataAgentSchema)
builder.add_node("router_node", router_node)
builder.add_node("etl_node", etl_node)
builder.add_node("sql_node", sql_node)

builder.add_edge(START, "router_node")
builder.add_conditional_edges("router_node", route_edge, {
    "sql_node": "sql_node",
    "etl_node": "etl_node"
})
builder.add_edge("sql_node", END)
builder.add_edge("etl_node", END)

data_agent = builder.compile()


if __name__ == "__main__":
    print("Testing Data Agent Router...")
    res = data_agent.invoke({
        "messages": [HumanMessage(content="Show me how many rides were completed in total")]
    })
    print("Response:", res["messages"][-1].content)