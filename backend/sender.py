#!/usr/bin/env python3
"""Email Sender module for loading contacts, queueing messages, and dispatching emails."""

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import config


import db


def get_db_connection() -> sqlite3.Connection:
    """Establish connection to SQLite database and ensure tables exist."""
    conn = sqlite3.connect(config.DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def load_contacts(csv_filepath: str, user_id: Optional[int] = None) -> None:
    """Load contacts from a CSV file into the SQLite database."""
    csv_path = Path(csv_filepath)
    if not csv_path.exists():
        print(f"Error: File not found at '{csv_filepath}'", file=sys.stderr)
        sys.exit(1)

    conn = get_db_connection()
    inserted_count = 0
    duplicate_count = 0

    if user_id is None:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
        row_u = cur.fetchone()
        user_id = row_u[0] if row_u else 1

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("Error: CSV file has no header row.", file=sys.stderr)
            sys.exit(1)

        # Normalize field names to lower-case
        field_map = {col.strip().lower(): col for col in reader.fieldnames}
        if "email" not in field_map or "name" not in field_map:
            print("Error: CSV must include 'name' and 'email' columns.", file=sys.stderr)
            sys.exit(1)

        email_key = field_map["email"]
        name_key = field_map["name"]

        now_str = datetime.utcnow().isoformat()

        for row in reader:
            email = row[email_key].strip()
            name = row[name_key].strip()
            if not email:
                continue

            # Check for group / group_tag column
            group_key = field_map.get("group") or field_map.get("group_tag")
            group_val = row[group_key].strip() if group_key and row.get(group_key) else None

            # Capture remaining fields as JSON in extra (including body if present)
            extra = {k: v for k, v in row.items() if k not in (email_key, name_key, group_key)}
            extra_json = json.dumps(extra) if extra else None

            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO contacts (email, name, extra_data, extra, group_tag, status, created_at, user_id)
                        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                        """,
                        (email, name, extra_json, extra_json, group_val, now_str, user_id),
                    )
                inserted_count += 1
            except sqlite3.IntegrityError:
                duplicate_count += 1

    conn.close()
    print(f"Successfully loaded {inserted_count} contact(s) from '{csv_path.name}'.")
    if duplicate_count > 0:
        print(f"Skipped {duplicate_count} duplicate contact(s).")


def show_status() -> None:
    """Display summary counts of contacts in the queue."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM contacts")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT status, COUNT(*) FROM contacts GROUP BY status")
    breakdown = dict(cursor.fetchall())

    conn.close()

    print("\n--- Mail Agent Queue Status ---")
    print(f"Database:     {config.DB_PATH}")
    print(f"Total:        {total}")
    print(f"Pending:      {breakdown.get('pending', 0)}")
    print(f"Sent:         {breakdown.get('sent', 0)}")
    print(f"Failed:       {breakdown.get('failed', 0)}")
    print(f"Provider:     {config.PROVIDER}")
    print(f"Daily Cap:    {config.DAILY_CAP}")
    print(f"Test Mode:    {config.TEST_MODE}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Email Assistant - Sender CLI",
        epilog="Use 'load <file.csv>' to import contacts or 'status' to review current queue.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: load
    load_parser = subparsers.add_parser("load", help="Load contacts from a CSV file into SQLite")
    load_parser.add_argument("csv_file", type=str, help="Path to contacts CSV file")

    # Subcommand: status
    subparsers.add_parser("status", help="Show current queue and contact counts")

    args = parser.parse_args()

    if args.command == "load":
        load_contacts(args.csv_file)
    elif args.command == "status":
        show_status()


if __name__ == "__main__":
    main()
