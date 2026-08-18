"""
seed.py — builds store.db (SQLite) with a small, synthetic store dataset.

This file is DONE FOR YOU on purpose: building a database is not the thing you're
here to learn. Read it so you know the schema (your agent will have to discover it
at runtime through the MCP tools — but YOU should know the answers to check its work).

Run once:  python seed.py
Re-running wipes and rebuilds, so it's safe.
"""

import sqlite3
from pathlib import Path

DB = Path(__file__).with_name("store.db")

SCHEMA = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS products;

CREATE TABLE products (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL,
    price  REAL NOT NULL          -- unit price in dollars
);

CREATE TABLE customers (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL,
    email  TEXT NOT NULL
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date  TEXT NOT NULL     -- ISO date 'YYYY-MM-DD'
);

CREATE TABLE order_items (
    id         INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL
);
"""

PRODUCTS = [
    (1, "Mechanical Keyboard", 120.0),
    (2, "Wireless Mouse", 45.0),
    (3, "27-inch Monitor", 340.0),
    (4, "USB-C Hub", 60.0),
    (5, "Laptop Stand", 35.0),
    (6, "Noise-Cancelling Headphones", 280.0),  # never ordered (for the anti-join question)
]

CUSTOMERS = [
    (1, "Ada Lovelace", "ada@example.com"),
    (2, "Alan Turing", "alan@example.com"),
    (3, "Grace Hopper", "grace@example.com"),
]

# (order_id, customer_id, date)
ORDERS = [
    (1, 1, "2026-06-01"),
    (2, 1, "2026-06-15"),
    (3, 2, "2026-06-20"),
    (4, 3, "2026-07-02"),
    (5, 1, "2026-07-10"),
]

# (id, order_id, product_id, quantity)
ORDER_ITEMS = [
    (1, 1, 1, 1),   # Ada: keyboard
    (2, 1, 2, 2),   # Ada: 2 mice
    (3, 2, 3, 1),   # Ada: monitor
    (4, 3, 5, 1),   # Alan: laptop stand
    (5, 4, 4, 3),   # Grace: 3 hubs
    (6, 5, 3, 1),   # Ada: another monitor
    (7, 5, 1, 1),   # Ada: another keyboard
]


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO products VALUES (?,?,?)", PRODUCTS)
    conn.executemany("INSERT INTO customers VALUES (?,?,?)", CUSTOMERS)
    conn.executemany("INSERT INTO orders VALUES (?,?,?)", ORDERS)
    conn.executemany("INSERT INTO order_items VALUES (?,?,?,?)", ORDER_ITEMS)
    conn.commit()
    conn.close()
    print(f"Built {DB.name}. Ada should be the top spender; headphones were never ordered.")


if __name__ == "__main__":
    main()
