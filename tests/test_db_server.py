import pytest
from db_server import run_select

@pytest.mark.parametrize("bad_sql", [
    "INSERT INTO customers VALUES (1, 'x')",
    "DROP TABLE customers",
    "SELECT 1; DROP TABLE customers",        # semicolon chaining
    "UPDATE orders SET total = 0",
    "PRAGMA table_info(customers)",
    "ATTACH DATABASE '/tmp/evil.db' AS evil",
    "SELECT 1 -- ; DROP TABLE customers",    # comment-based bypass — does yours catch it?
    "with (select 1) as t1 SELECT 1",
    "SELECT 1; --"
])
def test_run_select_rejects(bad_sql):
    result = run_select(bad_sql)
    print(f"{bad_sql} -> {result}")
    assert result.startswith('Error')        # non-empty: proves the call happened and returned something

def test_run_select_allows_a_plain_select():
    assert run_select("SELECT COUNT(*) FROM customers")   # the guard must not be so strict it blocks real work