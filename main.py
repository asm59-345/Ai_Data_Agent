import os
import sys
import argparse
from langchain_core.messages import HumanMessage
from agents.data_agent import data_agent


def run_cli_query(query: str):
    print(f"\n[AI Data Agent] Processing Query: '{query}'")
    response = data_agent.invoke({
        "messages": [HumanMessage(content=query)],
        "route_response": ""
    })
    last_msg = response["messages"][-1].content
    print("\n" + "=" * 50)
    print("Agent Response:")
    print("=" * 50)
    print(last_msg)
    print("=" * 50 + "\n")


def start_server(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    print(f"\n[AI Data Agent] Starting Web Server on http://{host}:{port}")
    uvicorn.run("api.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Data Agent CLI & Web Server")
    parser.add_argument("--query", "-q", type=str, help="Natural language query to process via CLI")
    parser.add_argument("--serve", "-s", action="store_true", help="Launch the Web Dashboard server")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host (default: 127.0.0.1)")

    args = parser.parse_args()

    if args.serve:
        start_server(host=args.host, port=args.port)
    elif args.query:
        run_cli_query(args.query)
    else:
        # Default demonstration query if executed with no arguments
        default_query = "What are the top 3 most popular vehicle makes in the database?"
        print("No arguments provided. Running demonstration query:")
        run_cli_query(default_query)