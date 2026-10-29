import argparse
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


DATABASE_PATH = Path(__file__).with_name("grievance.db")
PRIORITIES = ("Critical", "High", "Medium", "Low")
STATUSES = ("Pending", "In Progress", "Resolved", "Rejected", "Escalated")
PRIORITY_HOURS = {"Critical": 24, "High": 72, "Medium": 120, "Low": 168}


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def seed(database_path, confirm):
    database_path = Path(database_path)
    if not database_path.is_file():
        raise RuntimeError(f"Database file does not exist: {database_path}")
    if not confirm:
        print(
            "Dry run only. No database rows were changed. "
            f"Review the plan, then run with --confirm to seed {database_path}."
        )
    connection_target = (
        str(database_path.resolve())
        if confirm
        else f"{database_path.resolve().as_uri()}?mode=ro"
    )
    connection = sqlite3.connect(connection_target, uri=not confirm)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        required_tables = {"users", "departments", "complaints"}
        missing_tables = required_tables - tables
        if missing_tables:
            raise RuntimeError(f"Database is missing required tables: {', '.join(sorted(missing_tables))}")

        complaint_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(complaints)")
        }
        required_columns = {
            "complaint_id", "user_id", "title", "description", "category",
            "location", "priority", "department", "status", "deadline",
            "resolution", "created_at", "updated_at",
        }
        missing_columns = required_columns - complaint_columns
        if missing_columns:
            raise RuntimeError(f"Complaints table is missing required columns: {', '.join(sorted(missing_columns))}")

        admin = connection.execute(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"
        ).fetchone()
        if not admin:
            raise RuntimeError("Seeding requires an existing administrator user; no user records were changed.")
        departments = connection.execute(
            "SELECT id, name FROM departments WHERE TRIM(name) != '' ORDER BY id"
        ).fetchall()
        if not departments:
            raise RuntimeError("No departments are present; no complaint rows were changed.")

        plan = len(departments) * len(PRIORITIES) * len(STATUSES)
        if not confirm:
            print(f"Planned synthetic complaints: {plan} across {len(departments)} existing departments.")
            return 0

        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        inserted = 0
        duplicates = 0
        connection.execute("BEGIN IMMEDIATE")
        for department in departments:
            for priority in PRIORITIES:
                for status in STATUSES:
                    complaint_id = (
                        f"DEMO-{department['id']:04d}-{slug(priority)}-{slug(status)}"
                    )
                    exists = connection.execute(
                        "SELECT 1 FROM complaints WHERE complaint_id = ?",
                        (complaint_id,),
                    ).fetchone()
                    if exists:
                        duplicates += 1
                        continue

                    deadline = (
                        now + timedelta(hours=PRIORITY_HOURS[priority])
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    title = f"SYNTHETIC DEMO - {department['name']} - {priority} - {status}"
                    description = (
                        "Synthetic dashboard demonstration data created by "
                        "seed_department_demo_data.py. This is not a real complaint."
                    )
                    connection.execute(
                        """
                        INSERT INTO complaints (
                            complaint_id, user_id, title, description, category,
                            location, priority, department, status, deadline,
                            resolution, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            complaint_id,
                            admin["id"],
                            title,
                            description,
                            "Synthetic Demo",
                            f"SYNTHETIC DEMO - {department['name']}",
                            priority,
                            department["name"],
                            status,
                            deadline,
                            "Synthetic demo resolution only." if status == "Resolved" else None,
                            timestamp,
                            timestamp,
                        ),
                    )
                    inserted += 1
        connection.commit()
        print(
            f"Inserted {inserted} synthetic complaints; skipped {duplicates} "
            f"already-seeded IDs across {len(departments)} departments."
        )
        return inserted
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Seed clearly labelled, repeatable department dashboard demo complaints."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DATABASE_PATH,
        help=f"SQLite database to target (default: {DATABASE_PATH})",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Insert synthetic complaint rows after printing no changes by default.",
    )
    args = parser.parse_args()
    try:
        seed(args.database, args.confirm)
    except (OSError, sqlite3.Error, RuntimeError) as error:
        parser.exit(1, f"Seeding stopped: {error}\n")


if __name__ == "__main__":
    main()
