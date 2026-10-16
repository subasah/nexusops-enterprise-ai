"""
NexusOps Enterprise Relational Database Layer.

Provides ACID-compliant relational data persistence with automatic schema migration,
seed state generation, transaction safety, and comprehensive audit logging.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional


class DatabaseService:
    """Enterprise relational database simulation backed by SQLite."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self.seed_defaults()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                tier TEXT NOT NULL DEFAULT 'STANDARD', -- 'VIP', 'ENTERPRISE', 'STANDARD'
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                balance_usd REAL NOT NULL DEFAULT 0.0,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                amount_usd REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                status TEXT NOT NULL DEFAULT 'COMPLETED', -- 'PENDING', 'COMPLETED', 'REFUNDED', 'DISPUTED'
                created_at REAL NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS invoices (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                amount_usd REAL NOT NULL,
                is_paid INTEGER NOT NULL DEFAULT 1,
                due_date TEXT NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                details TEXT NOT NULL,
                timestamp REAL NOT NULL
            );
            """)

    def seed_defaults(self) -> None:
        """Seeds realistic enterprise customer and billing state."""
        with self._conn:
            self._conn.execute("DELETE FROM invoices")
            self._conn.execute("DELETE FROM orders")
            self._conn.execute("DELETE FROM customers")
            self._conn.execute("DELETE FROM audit_logs")

            now = time.time()
            # Seed Customers
            customers = [
                ("CUST-901", "Acme Global Corp", "billing@acmeglobal.com", "VIP", "ACTIVE", 0.0, now - 86400 * 30),
                ("CUST-902", "Nova Dynamics", "ops@novadynamics.io", "ENTERPRISE", "ACTIVE", 150.0, now - 86400 * 60),
                ("CUST-903", "Apex Retailers", "accounts@apexretail.org", "STANDARD", "ACTIVE", 0.0, now - 86400 * 15),
            ]
            self._conn.executemany(
                "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)", customers
            )

            # Seed Orders
            orders = [
                ("ORD-7701", "CUST-901", 1450.00, "USD", "COMPLETED", now - 86400 * 2),
                ("ORD-7702", "CUST-901", 189.50, "USD", "COMPLETED", now - 86400 * 1),
                ("ORD-7703", "CUST-902", 5200.00, "USD", "COMPLETED", now - 86400 * 5),
                ("ORD-7704", "CUST-903", 75.00, "USD", "COMPLETED", now - 86400 * 3),
            ]
            self._conn.executemany(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", orders
            )

            # Seed Invoices
            invoices = [
                ("INV-8801", "ORD-7701", "CUST-901", 1450.00, 1, "2026-11-01"),
                ("INV-8802", "ORD-7702", "CUST-901", 189.50, 1, "2026-11-02"),
                ("INV-8803", "ORD-7703", "CUST-902", 5200.00, 1, "2026-11-05"),
                ("INV-8804", "ORD-7704", "CUST-903", 75.00, 1, "2026-11-03"),
            ]
            self._conn.executemany(
                "INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)", invoices
            )

    def get_customer_by_id(self, customer_id: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_customer_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.execute("SELECT * FROM customers WHERE LOWER(email) = LOWER(?)", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_orders_by_customer(self, customer_id: str) -> List[Dict[str, Any]]:
        cursor = self._conn.execute("SELECT * FROM orders WHERE customer_id = ?", (customer_id,))
        return [dict(r) for r in cursor.fetchall()]

    def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_invoice_by_id(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_order_status(self, order_id: str, new_status: str, actor: str = "agent") -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id)
            )
            if cursor.rowcount > 0:
                self.record_audit_log(
                    actor=actor,
                    action="UPDATE_ORDER_STATUS",
                    entity_type="ORDER",
                    entity_id=order_id,
                    details={"new_status": new_status}
                )
                return True
            return False

    def record_audit_log(
        self, actor: str, action: str, entity_type: str, entity_id: str, details: Dict[str, Any]
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO audit_logs (actor, action, entity_type, entity_id, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (actor, action, entity_type, entity_id, json.dumps(details), time.time())
            )

    def get_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self._conn.execute(
            "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        logs = []
        for r in cursor.fetchall():
            d = dict(r)
            try:
                d["details"] = json.loads(d["details"])
            except Exception:
                pass
            logs.append(d)
        return logs
