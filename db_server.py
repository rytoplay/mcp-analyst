"""
db_server.py — an MCP server exposing READ tools over store.db.

Analogy for your PHP/Perl brain: this is a tiny microservice. Each @mcp.tool() is
an endpoint with a typed contract. The difference from a REST API is that the CLIENT
DISCOVERS these tools at runtime (list_tools) instead of you hardcoding a schema —
that's the whole MCP value proposition you saw in Module 15.

Run standalone to sanity-check it starts:  python db_server.py
(It speaks MCP over stdio, so it'll just sit waiting — that's correct. Ctrl-C to quit.)

ONE tool (list_tables) is written for you as the reference pattern.
Write the other three: describe_table, run_select, sample_rows.
"""

import sqlite3
from pathlib import Path
import re

from mcp.server.fastmcp import FastMCP   # canonical package: pip install mcp

DB = Path(__file__).with_name("store.db")
mcp = FastMCP("Store DB Analyst")


def _connect() -> sqlite3.Connection:
    """Open a fresh read-oriented connection. (Each call opens its own — simplest.)"""
    return sqlite3.connect(DB)


# ---- WORKED EXAMPLE: study this, then mirror the pattern for the rest ----------
@mcp.tool()
def list_tables() -> str:
    """List the names of all tables in the database. Call this first to orient yourself."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return "\n".join(r[0] for r in rows) or "(no tables)"
    finally:
        conn.close()


# ---- YOUR TURN -----------------------------------------------------------------

@mcp.tool()
def describe_table(table: str) -> str:
    """Return the column names and types for one table, so the model can write valid SQL.

    Uses PRAGMA table_info(<table>), which returns (cid, name, type, notnull, default, pk).
    WATCH OUT: `table` comes from the model — you can't parameter-bind a table name into
    PRAGMA. Validate it against list_tables() output first, or you've built a SQL-injection hole.
    Return something readable, e.g.  "id INTEGER, name TEXT, price REAL".
    """
    conn = _connect()
    if table not in list_tables().split("\n"):
        return "Error: bad table name"
    try:
        schema = conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
        result = []
        for r in schema:
            result.append(f"{r[1]} {r[2]}")
        return ", ".join(result)
    finally:
        conn.close()


    raise NotImplementedError


@mcp.tool()
def run_select(sql: str) -> str:
    """Run a single read-only SELECT and return the rows as text.

    SECURITY-CRITICAL. The model writes this SQL, which makes it untrusted input from a
    non-deterministic source. Anything that isn't a lone SELECT is refused. Rejects when:
      - after stripping, it doesn't start with SELECT (case-insensitive)
      - it contains a ';' (blocks statement-chaining like  SELECT 1; DROP TABLE ...)
      - it contains any of: insert update delete drop alter attach pragma create replace
    On rejection it RETURNS an error string rather than raising: the model sees the refusal
    and can try a different query. That feedback loop is deliberate.

    Results are formatted as a header row plus rows (column names from cursor.description),
    and capped so a large result set can't blow up the prompt.
    """


    keywords = ['insert', 'update', 'delete', 'drop', 'alter', 'attach', 'pragma', 'create', 'replace']
    for keyword in keywords:
        if re.search(rf'\b{keyword}\b', sql, re.IGNORECASE):
            return "Error: incorrect SQL"

    if not sql.lower().startswith("select"):
        return "Error: incorrect SQL"

    if ";" in sql:
        return "Error: sql injection error. No semicolons permitted."

    if not re.search(r'\blimit\b', sql, re.IGNORECASE): sql += " LIMIT 500"

    conn = _connect()
    try:
        cursor = conn.execute(sql)
        result = cursor.fetchall()
        rslt = ", ".join(col[0] for col in cursor.description) + "\n"
        rslt += "\n".join([", ".join(str(v) for v in r) for r in result])
        return rslt

        
    finally:
        conn.close()


@mcp.tool()
def sample_rows(table: str, n: int = 3) -> str:
    """Return the first `n` rows of a table as text — handy for the model to see real values.

    Reuse your table-name validation from describe_table (don't duplicate the injection hole).
    """
    if table not in list_tables().split("\n"):
        return "Error: bad table name"

    return run_select(f"SELECT * FROM {table} LIMIT {n}")

if __name__ == "__main__":
    mcp.run()   # defaults to stdio transport
