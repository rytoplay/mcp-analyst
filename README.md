# mcp-analyst

A natural-language database analyst built on the **Model Context Protocol** — implemented
from **both sides**, and driven by a **local** model with no native tool-calling.

Ask it a question in English; it explores the schema, writes SQL, and answers from the
results:

```bash
python agent.py "Which customer has spent the most, and on what products?"
```

To answer that, the model has to chain three tool calls — it doesn't know the schema, so it
can't write the query blind:

```
list_tables()                    → what tables exist?
describe_table("order_items")    → what columns?
run_select("SELECT ... JOIN ... GROUP BY ... ORDER BY ... LIMIT 1")
```

That forced explore-then-act sequence is the agentic behavior. Everything below exists to
make a model that *cannot natively call tools* perform it reliably.

---

## Three things this demonstrates

### 1. Both sides of MCP

`db_server.py` is an **MCP server** exposing four tools over SQLite. It works with any MCP
host — Claude Code discovers and calls it with zero integration code.

`agent.py` is an **MCP client**, written by hand. Most people only ever consume MCP through a
host that implements the client for them; this implements the client side directly.

### 2. Tool-calling for a model that has no tool-calling

gemma2:9b returns HTTP 400 if you send it a `tools=` parameter. It has no structured
tool-call support at all. So the contract is imposed through the system prompt:

> Respond with exactly ONE JSON object and nothing else. Either
> `{"tool": "<name>", "arguments": {...}}` to call a tool, or
> `{"answer": "..."}` when you have enough to answer.

with `format="json"` on the Ollama call to force parseable output, then hand-parsing and
dispatching each reply. Doing this by hand is what makes the native-tool-calling APIs legible
— you can see exactly which affordance you're reimplementing.

The system prompt is generated from the server's **advertised** tool schema
(`session.list_tools()`), not a hardcoded list — which is what makes the next part work.

### 3. The client is protocol-general, and that's provable

Swap in a **third-party public MCP server** — `mcp-sqlite`, one `npx` command — and the same
client code drives it unchanged:

```bash
MCP_SERVER=own python agent.py "How many orders were placed?"   # db_server.py, in this repo
MCP_SERVER=npx python agent.py "How many orders were placed?"   # public mcp-sqlite (default)
```

That's the actual value of the protocol: not that you can wrap your own tools, but that any
published server becomes usable with no per-tool integration work.

---

## The security guard

`run_select` accepts SQL **written by a language model**. That is untrusted input from a
non-deterministic source, and the interesting framing is that *the untrusted party is the
model itself* — which is the shape most prompt-injection risk takes once you give a model
tools.

The guard rejects anything that isn't a single read-only `SELECT`:

- must start with `SELECT` after stripping
- no `;` — blocks statement chaining (`SELECT 1; DROP TABLE ...`)
- no `insert`, `update`, `delete`, `drop`, `alter`, `attach`, `pragma`, `create`, `replace`
- row cap, so a huge result can't blow up the context window

On rejection it **returns an error string rather than raising** — the model sees the refusal
and retries with a different query. That feedback loop is deliberate.

---

## A debugging finding worth writing down

gemma2 kept answering only the **first half** of two-part questions ("which customer spent the
most, *and on what products?*"). Ten system-prompt rewrites changed nothing.

What fixed it was moving the instruction rather than rewriting it: after **every tool result**,
a completion check is re-injected into the conversation asking whether the result satisfies
every distinct part of the original question, and to call another tool if not.

The failure was never comprehension — it was **salience**. The "am I done?" decision happens
immediately after a tool result, and by that point the original instruction is buried under
accumulated tool output. A model with native tool-calling maintains multi-part task state
across iterations. When you build the loop yourself, you have to supply that state explicitly.

---

## Architecture

```
  question (English)
        │
        ▼
  agent.py  ──(Ollama /api/chat, gemma2:9b, no tools=)──►  gemma2:9b
   │  ▲                                                        │
   │  │  parse JSON: {"tool":...} or {"answer":...}            │
   │  └────────────────────────────────────────────────────────┘
   │
   │  MCP client: session.call_tool()
   ▼
  db_server.py  (MCP server over stdio, FastMCP)   ── or ──  npx mcp-sqlite
   │
   ▼
  store.db  (SQLite, built by seed.py)
```

| File | Role |
|---|---|
| `agent.py` | MCP client + ReAct loop + the hand-rolled JSON tool-calling contract |
| `db_server.py` | MCP server — `list_tables`, `describe_table`, `run_select`, `sample_rows` |
| `seed.py` | Builds `store.db` (products, customers, orders, order_items) |

---

## Running it

Requires Python 3.12+, [Ollama](https://ollama.com) with `gemma2:9b` pulled, and Node (for the
optional `npx` server).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install mcp
python seed.py                 # builds store.db
ollama pull gemma2:9b

python agent.py "How many customers are there?"
python agent.py "Which customer has spent the most, and on what products?"
python agent.py "Which product has never been ordered?"
```

Each step of the loop prints, so you can watch the model chain
`list_tables → describe_table → run_select` rather than taking it on faith.

---

## Notes

- `MAX_STEPS` caps the loop. Without it a confused model runs forever on a question it can't
  answer — a real concern in any agentic system, not a toy safeguard.
- The MCP client is async while the Ollama call is a blocking HTTP request. Fine at this
  scale; a production version would want an async HTTP client.
- Swapping gemma2 for a model with native tool-calling (`qwen2.5:7b`) against the same server
  is a direct way to feel what the hand-rolled protocol is standing in for.
