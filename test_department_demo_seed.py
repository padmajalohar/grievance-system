from contextlib import closing
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
SEED_SCRIPT = PROJECT / "seed_department_demo_data.py"


class DepartmentDemoSeederTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="resolveai-demo-seed-")
        self.database = Path(self.temp_dir.name) / "demo.sqlite"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL
                );
                CREATE TABLE departments (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE complaints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    complaint_id TEXT NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT,
                    location TEXT,
                    priority TEXT,
                    department TEXT,
                    status TEXT NOT NULL,
                    deadline TEXT,
                    resolution TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                INSERT INTO users VALUES
                    (1, 'Existing Admin', 'admin@example.test', 'unchanged-admin-hash', 'admin'),
                    (2, 'Existing Citizen', 'citizen@example.test', 'unchanged-citizen-hash', 'citizen');
                INSERT INTO departments VALUES
                    (1, 'Water Supply Department', 'water supply department', '2026-01-01T00:00:00Z'),
                    (2, 'Sanitation Department', 'sanitation department', '2026-01-01T00:00:00Z');
                INSERT INTO complaints (
                    complaint_id, user_id, title, description, category, location,
                    priority, department, status, deadline, resolution, created_at, updated_at
                ) VALUES (
                    'REAL-001', 2, 'Existing real complaint', 'Preserve exactly.',
                    'Water Supply', 'Existing location', 'High',
                    'Water Supply Department', 'Pending', NULL, NULL,
                    '2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z'
                );
                """
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_seeder(self, *args):
        return subprocess.run(
            [sys.executable, str(SEED_SCRIPT), "--database", str(self.database), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_seed_is_opt_in_repeatable_and_preserves_existing_rows(self):
        with closing(sqlite3.connect(self.database)) as connection:
            before_users = connection.execute("SELECT * FROM users ORDER BY id").fetchall()
            before_real = connection.execute(
                "SELECT * FROM complaints WHERE complaint_id = 'REAL-001'"
            ).fetchall()

        dry_run = self.run_seeder()
        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        self.assertIn("Dry run only", dry_run.stdout)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM complaints").fetchone()[0], 1)

        seeded = self.run_seeder("--confirm")
        self.assertEqual(seeded.returncode, 0, seeded.stderr)
        self.assertIn("Inserted 40 synthetic complaints", seeded.stdout)
        with closing(sqlite3.connect(self.database)) as connection:
            seeded_rows = connection.execute(
                "SELECT complaint_id, title, description, department, priority, status "
                "FROM complaints WHERE complaint_id LIKE 'DEMO-%' ORDER BY complaint_id"
            ).fetchall()
            self.assertEqual(len(seeded_rows), 40)
            self.assertTrue(all(row[1].startswith("SYNTHETIC DEMO - ") for row in seeded_rows))
            self.assertTrue(all("not a real complaint" in row[2] for row in seeded_rows))
            self.assertEqual(
                connection.execute("SELECT * FROM users ORDER BY id").fetchall(),
                before_users,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT * FROM complaints WHERE complaint_id = 'REAL-001'"
                ).fetchall(),
                before_real,
            )
            combos = {(row[3], row[4], row[5]) for row in seeded_rows}
            self.assertEqual(len(combos), 2 * 4 * 5)

        repeated = self.run_seeder("--confirm")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn("Inserted 0 synthetic complaints; skipped 40", repeated.stdout)


if __name__ == "__main__":
    unittest.main()
