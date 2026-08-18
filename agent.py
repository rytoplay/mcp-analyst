"""
agent.py — the MCP client and ReAct loop.

A local model (gemma2:9b via Ollama) answers English questions about a SQLite database by
chaining MCP tool calls. gemma2 has no native tool-calling, so the JSON protocol that lets
it request a tool is imposed here, by hand, through the system prompt.

Run:  python agent.py "Which customer spent the most, and on what products?"

The loop:
  1. Discover the server's tools through the MCP client (list_tools).
  2. Build a system prompt describing those tools and the JSON contract.
  3. Repeat until the model produces an answer or MAX_STEPS is hit:
       - call Ollama (no tools= param; format="json" forces parseable output)
       - parse the reply
       - {"tool": name, "arguments": {...}}  -> dispatch over MCP, append the result, loop
       - {"answer": "..."}                   -> print and stop

The step cap matters: without it a confused model loops forever, burning tokens on a
question it cannot answer.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma2:9b"
MAX_STEPS = 18


def ollama_chat(messages: list[dict]) -> str:
    """POST messages to Ollama and return the assistant's raw text content.

    `format="json"` makes gemma2 emit valid JSON, which is what keeps the parser simple.

    Note there is deliberately no "tools" key in the body: gemma2 has no native
    tool-calling and returns HTTP 400 if one is sent. That absence is the whole reason
    the JSON contract in build_system_prompt() exists.
    """
    # Data payload dictionary
    payload = {"model": MODEL, "messages": messages, "stream": False, "format": "json"}

    # 1. Convert dictionary to a JSON string and encode it to raw bytes
    json_data = json.dumps(payload).encode("utf-8")

    # 2. Construct the Request object and specify the POST method
    req = urllib.request.Request(
        OLLAMA_URL, data=json_data, method="POST", headers={"Content-Type": "application/json"}
    )

    # 3. Send the request and read the server response
    try:
        with urllib.request.urlopen(req) as response:
            # Read and decode response payload
            response_body = response.read().decode("utf-8")
            response_json = json.loads(response_body)
            return response_json["message"]["content"]
    except urllib.error.HTTPError as e:
        return f"HTTP Error: {e.code} - {e.reason}"
    except urllib.error.URLError as e:
        return f"URL Error: {e.reason}"


def build_system_prompt(tools) -> str:
    """Turn the discovered MCP tools into instructions gemma2 can follow.

    `tools` is whatever session.list_tools() returned — note the prompt is built from
    the server's own advertised schema, not from a hardcoded list. That's what lets the
    same client drive a different MCP server without code changes.

    The prompt establishes the contract: reply with exactly ONE JSON object, either
        {"tool": "<name>", "arguments": {...}}
    or
        {"answer": "<final answer for the user>"}
    plus the instruction to explore the schema before writing SQL and to ground the
    final answer only in tool results.
    """

    tool_list = []
    for t in tools.tools:
        tool_list.append(f"- {t.name}: {t.description} (arguments: {", ".join(t.inputSchema.get("properties", {}).keys())})")
    tool_list_string = "\n".join(tool_list)
    prompt = f"""
    You are a database query building expert. You are being asked a question which you will answer by calling the following tools
    from the database. Be sure to answer the entire question. Use the database table structure to determine which fields contain
    the information the user is requesting and double check that the answer matches the user's question.
    You are a database analyst. You have access to the following tools:

{tool_list_string}

Respond with exactly ONE JSON object and nothing else. To call a tool:
{{"tool": "<name>", "arguments": {{...}}}}

When you have enough information to answer the user's question, respond with:
{{"answer": "<your final answer>"}}

Always call list_tables and describe_table first to understand the schema before writing
any SQL query. Base your final answer only on the results returned by tool calls — never
guess or make up numbers.

Before producing a final answer, identify every distinct piece of information requested by the user.

For each requested item, verify that the results returned by your tool calls provide the necessary evidence.

If any requested information is missing, continue calling tools and running SQL queries until every requested item has been retrieved.

Run as many queries as necessary.

Do not assume that one successful SQL query answers the entire question.

Do not respond with {{“answer”: …}} until every part of the user’s question is supported by tool results.
"""

    return prompt


def tool_result_text(result) -> str:
    """Extract plain text from an MCP call_tool result.

    call_tool returns content blocks, not a string — the text lives at content[0].text.
    """
    return result.content[0].text


async def run(question: str) -> None:
    # Two interchangeable servers, same client code — that interchangeability is the
    # point of the protocol:
    #   MCP_SERVER=own   -> db_server.py, the MCP server in this repo
    #   MCP_SERVER=npx   -> mcp-sqlite, a public third-party server (default)
    db_path = str(Path(__file__).parent / "store.db")

    if os.environ.get("MCP_SERVER", "npx") == "own":
        server = StdioServerParameters(command=sys.executable, args=["db_server.py"])
    else:
        server = StdioServerParameters(command="npx", args=["-y", "mcp-sqlite", db_path])

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()

            messages = [
                {"role": "system", "content": build_system_prompt(tools)},
                {"role": "user", "content": question},
            ]

            for step in range(MAX_STEPS):
                reply = ollama_chat(messages)
                messages.append({"role": "assistant", "content": reply})
                print(f"\n\nREPLY: {reply}")
                parsed = json.loads(reply)
                print(f"\nPARSED: {parsed}")
                args = parsed.get("arguments", {})
                if "answer" in parsed:
                    print(parsed["answer"])
                    return
                elif "tool" in parsed:
                    result = await session.call_tool(parsed["tool"], arguments=args)
                    result_text = tool_result_text(result)
                    #messages.append({"role": "user", "content": f"Result of {parsed['tool']}: {result_text}"})
                    messages.append({
                        "role": "user",
                        "content": f"""
                    Tool result from {parsed['tool']}:
                    {result_text}
                    Original user question:
                    {question}
                    Review the original question again. Determine whether this tool result
                    provides every distinct piece of information requested.
                    If any requested information is still missing, call another tool.
                    Return an answer only when all requested information is present in the
                    tool results.
                    """.strip()
                })
                #   If it has "tool": call session.call_tool(name, arguments=args),
                #   turn the result into text (tool_result_text), print the step so you can
                #   SEE the chain, then append it as a new message, e.g.:
                #     messages.append({"role": "user",
                #       "content": f'Result of {name}: {result_text}'})
                #   Handle bad JSON / unknown tool by feeding an error message back so the
                #   model can recover instead of crashing.
                #raise NotImplementedError

            print("Hit MAX_STEPS without a final answer — the model got stuck.")


if __name__ == "__main__":
    import asyncio

    q = sys.argv[1] if len(sys.argv) > 1 else "How many orders were placed?"
    asyncio.run(run(q))
