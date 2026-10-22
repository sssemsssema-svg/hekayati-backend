import os
import sqlite3
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import config

DB_PATH = Path(__file__).resolve().parent.parent / "orders.db"
AUDIO_DIR = config.OUTPUT_DIR / "orders_audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                child_name TEXT NOT NULL,
                child_gender TEXT NOT NULL,
                child_age TEXT NOT NULL,
                order_type TEXT NOT NULL,
                art_style TEXT NOT NULL,
                story_idea TEXT,
                audio_filename TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                notes TEXT,
                result_job_id TEXT
            )
        """)
        conn.commit()


def generate_order_id() -> str:
    today_str = datetime.now().strftime("%y%m%d")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders WHERE id LIKE ?", (f"HK-{today_str}%",))
        count = cursor.fetchone()[0] + 1
        return f"HK-{today_str}-{count:03d}"


def create_order(
    customer_name: str,
    customer_phone: str,
    child_name: str,
    child_gender: str,
    child_age: str,
    order_type: str,
    art_style: str,
    story_idea: str = "",
    audio_bytes: Optional[bytes] = None,
    audio_ext: str = ".m4a",
    notes: str = "",
) -> Dict[str, Any]:
    init_db()
    order_id = generate_order_id()
    created_at = datetime.now().isoformat()

    audio_filename = None
    if audio_bytes and len(audio_bytes) > 0:
        audio_filename = f"{order_id}{audio_ext}"
        audio_path = AUDIO_DIR / audio_filename
        audio_path.write_bytes(audio_bytes)

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO orders (
                id, created_at, customer_name, customer_phone, child_name,
                child_gender, child_age, order_type, art_style, story_idea,
                audio_filename, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                order_id,
                created_at,
                customer_name.strip(),
                customer_phone.strip(),
                child_name.strip(),
                child_gender.strip(),
                child_age.strip(),
                order_type.strip(),
                art_style.strip(),
                story_idea.strip(),
                audio_filename,
                notes.strip(),
            ),
        )
        conn.commit()

    return get_order(order_id)


def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)


def list_orders(status: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        if status and status != "all":
            cursor.execute("SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def update_order_status(order_id: str, status: str, result_job_id: Optional[str] = None) -> bool:
    init_db()
    with get_db() as conn:
        if result_job_id:
            conn.execute(
                "UPDATE orders SET status = ?, result_job_id = ? WHERE id = ?",
                (status, result_job_id, order_id),
            )
        else:
            conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        conn.commit()
        return conn.total_changes > 0


def get_order_audio_path(order_id: str) -> Optional[Path]:
    order = get_order(order_id)
    if not order or not order.get("audio_filename"):
        return None
    p = AUDIO_DIR / order["audio_filename"]
    return p if p.exists() else None
