import os
import sys
import re

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.llm_pick import pick_llm
from utils.etl_tools import ETLTools
from Models.schema import ETLAgentSchema
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain.tools import tool


@tool
def extract_load_tool(url: str, output_folder: str = "data/extract", format: str = "csv") -> str:
    """
    Extracts data from a REST API endpoint and saves it into the destination folder.

    Args:
        url (str): The HTTP/HTTPS API endpoint URL to fetch data from.
        output_folder (str): The folder where extracted data will be saved (default: 'data/extract').
        format (str): The file format: 'csv', 'json', or 'parquet'.
    """
    etl = ETLTools()
    return etl.extract_load(url, output_folder, format)


@tool
def transform_load_tool(input_file_path: str, output_folder: str = "data/transform", output_format: str = "csv", user_question: str = "") -> str:
    """
    Transforms data from an existing file using dynamic Pandas transformation logic.

    Args:
        input_file_path (str): The path to the source data file (CSV, JSON, or Parquet).
        output_folder (str): Target directory for transformed data (default: 'data/transform').
        output_format (str): Desired output format: 'csv', 'json', or 'parquet'.
        user_question (str): The analytical or transformation requirements requested by the user.
    """
    etl = ETLTools()
    context = etl.transform_load_context(input_file_path)

    llm = pick_llm("medium")
    prompt = f"""You are an expert Data Engineer using Python and Pandas.
Write Python code using Pandas to perform the required transformation on: '{input_file_path}'
and save the result to: '{output_folder}' in '{output_format}' format.

CRITICAL INSTRUCTIONS:
1. Provide valid Python code ONLY. No explanations, no markdown greetings.
2. Read the source file with pandas (pd.read_csv, pd.read_json, or pd.read_parquet).
3. Apply the requested transformations.
4. Ensure target directory exists (os.makedirs('{output_folder}', exist_ok=True)).
5. Save the output to '{output_folder}/transformed_data.{output_format}'.

User Transformation Requirement: {user_question}

Data Context Preview:
{context}
"""
    response = llm.invoke(prompt).content

    # Clean markdown code blocks
    pandas_code = response.strip()
    match = re.search(r"```(?:python)?\s*([\s\S]*?)\s*```", pandas_code, re.IGNORECASE)
    if match:
        pandas_code = match.group(1).strip()

    exec_result = etl.execute_code(pandas_code)
    return (
        f"ETL Transformation Status:\n"
        f"- Target Format: {output_format.upper()}\n"
        f"- Execution Details: {exec_result}\n"
        f"- Generated Script:\n```python\n{pandas_code}\n```"
    )


tools = [extract_load_tool, transform_load_tool]


def llm_node(state: ETLAgentSchema):
    """Processes user message and selects appropriate ETL tool."""
    messages = state.messages
    llm = pick_llm("medium")
    llm_with_tools = llm.bind_tools(tools)

    prompt = [
        AIMessage(content="You are an ETL Analyst Agent capable of extracting API data and transforming files using Pandas."),
    ] + messages

    response = llm_with_tools.invoke(prompt)
    return {"messages": [response]}


def tool_node(state: ETLAgentSchema):
    """Executes the chosen ETL tools."""
    tools_by_name = {t.name: t for t in tools}
    tool_calls = state.messages[-1].tool_calls
    results = []

    for call in tool_calls:
        tool_obj = tools_by_name.get(call["name"])
        if tool_obj:
            observation = tool_obj.invoke(call["args"])
        else:
            observation = f"Error: Tool '{call['name']}' not found."
        results.append(ToolMessage(content=str(observation), tool_call_id=call["id"]))

    return {"messages": results}


def is_tool_call(state: ETLAgentSchema) -> str:
    last_msg = state.messages[-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tool_node"
    return "end"


builder = StateGraph(ETLAgentSchema)
builder.add_node("llm_node", llm_node)
builder.add_node("tool_node", tool_node)

builder.add_edge(START, "llm_node")
builder.add_conditional_edges("llm_node", is_tool_call, {
    "tool_node": "tool_node",
    "end": END
})
builder.add_edge("tool_node", "llm_node")

etl_checkpointer = MemorySaver()
etl_analyst_hitl = builder.compile(checkpointer=etl_checkpointer, interrupt_before=["tool_node"])
etl_analyst = builder.compile()


if __name__ == "__main__":
    print("Testing ETL Analyst Agent...")
    res = etl_analyst.invoke({
        "messages": [HumanMessage(content="Extract data from https://jsonplaceholder.typicode.com/todos to data/extract as json")]
    })
    print(res["messages"][-1].content)