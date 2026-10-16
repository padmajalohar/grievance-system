import os
import re
import hashlib
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from html import escape
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "grievance.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EVIDENCE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "pdf", "doc", "docx"}

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
CORS(app, resources={r"/api/*": {"origins": "*"}})


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "Evidence files must be 8 MB or smaller."}), 413


@app.before_request
def block_public_evidence_files():
    if request.path.startswith("/uploads/"):
        return jsonify({"error": "Not found."}), 404
    return None

CATEGORY_TO_DEPARTMENT = {
    "Water Supply": "Water Supply Department",
    "Sanitation": "Sanitation Department",
    "Street Lighting": "Electrical & Street Lighting Department",
    "Roads / Public Works": "Public Works Department",
    "Drainage": "Drainage Department",
    "Administration": "Administration Office",
    "Campus Facilities": "Campus Facilities Department",
    "General Review": "Administrator Review Queue",
}

PRIORITY_SLA_HOURS = {
    "Critical": 24,
    "High": 72,
    "Medium": 120,
    "Low": 168,
}


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_dt(value: Optional[str]) -> str:
    if not value:
        return "-"
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime("%d %b %Y, %H:%M")
    except ValueError:
        return value


def init_db() -> None:
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'citizen' CHECK(role IN ('citizen','admin')),
            session_token TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS complaints (
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
            assigned_officer TEXT,
            evidence TEXT,
            deadline TEXT,
            escalation_reason TEXT,
            resolution TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS complaint_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            changed_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id)
        );

        CREATE TABLE IF NOT EXISTS ai_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT NOT NULL UNIQUE,
            predicted_category TEXT,
            predicted_priority TEXT,
            confidence REAL,
            recommended_department TEXT,
            model_version TEXT,
            requires_human_review INTEGER DEFAULT 0,
            prediction_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id)
        );

        CREATE TABLE IF NOT EXISTS escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            escalated_to TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(complaint_id, stage)
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER,
            actor_role TEXT,
            complaint_id TEXT,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reward_rules (
            rule_key TEXT PRIMARY KEY,
            points INTEGER NOT NULL CHECK(points >= 0),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS reward_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS badge_definitions (
            badge_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            contribution_threshold INTEGER NOT NULL CHECK(contribution_threshold >= 0),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS reward_reviews (
            complaint_id TEXT PRIMARY KEY,
            citizen_id INTEGER NOT NULL,
            eligible INTEGER NOT NULL CHECK(eligible IN (0, 1)),
            evidence_approved INTEGER NOT NULL DEFAULT 0 CHECK(evidence_approved IN (0, 1)),
            resolution_verified INTEGER NOT NULL DEFAULT 0 CHECK(resolution_verified IN (0, 1)),
            social_impact_verified INTEGER NOT NULL DEFAULT 0 CHECK(social_impact_verified IN (0, 1)),
            reason TEXT NOT NULL,
            administrator_id INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id),
            FOREIGN KEY (citizen_id) REFERENCES users(id),
            FOREIGN KEY (administrator_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS reward_review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT NOT NULL,
            citizen_id INTEGER NOT NULL,
            eligible INTEGER NOT NULL CHECK(eligible IN (0, 1)),
            evidence_approved INTEGER NOT NULL CHECK(evidence_approved IN (0, 1)),
            resolution_verified INTEGER NOT NULL CHECK(resolution_verified IN (0, 1)),
            social_impact_verified INTEGER NOT NULL CHECK(social_impact_verified IN (0, 1)),
            reason TEXT NOT NULL,
            administrator_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id),
            FOREIGN KEY (citizen_id) REFERENCES users(id),
            FOREIGN KEY (administrator_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS complaint_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT NOT NULL,
            citizen_id INTEGER NOT NULL,
            details TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'Pending' CHECK(review_status IN ('Pending', 'Verified', 'Rejected')),
            review_reason TEXT,
            reviewed_by INTEGER,
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id),
            FOREIGN KEY (citizen_id) REFERENCES users(id),
            FOREIGN KEY (reviewed_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS reward_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT NOT NULL UNIQUE,
            citizen_id INTEGER NOT NULL,
            complaint_id TEXT,
            update_id INTEGER,
            event_type TEXT NOT NULL,
            points INTEGER NOT NULL CHECK(points != 0),
            reason TEXT NOT NULL,
            event_key TEXT NOT NULL UNIQUE,
            authorized_by INTEGER,
            reversal_of INTEGER UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY (citizen_id) REFERENCES users(id),
            FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id),
            FOREIGN KEY (update_id) REFERENCES complaint_updates(id),
            FOREIGN KEY (authorized_by) REFERENCES users(id),
            FOREIGN KEY (reversal_of) REFERENCES reward_transactions(id)
        );

        CREATE TABLE IF NOT EXISTS citizen_badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            citizen_id INTEGER NOT NULL,
            badge_key TEXT NOT NULL,
            criteria_satisfied TEXT NOT NULL,
            awarded_at TEXT NOT NULL,
            revoked_at TEXT,
            revoked_reason TEXT,
            UNIQUE(citizen_id, badge_key),
            FOREIGN KEY (citizen_id) REFERENCES users(id),
            FOREIGN KEY (badge_key) REFERENCES badge_definitions(badge_key)
        );

        CREATE INDEX IF NOT EXISTS idx_reward_transactions_citizen ON reward_transactions(citizen_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_complaint_updates_review ON complaint_updates(review_status, created_at);
        CREATE INDEX IF NOT EXISTS idx_reward_reviews_citizen ON reward_reviews(citizen_id, eligible);
        """
    )
    conn.executemany(
        "INSERT OR IGNORE INTO reward_rules (rule_key, points, enabled) VALUES (?, ?, 1)",
        [("verified_contribution", 10), ("evidence_approved", 5), ("resolution_verified", 20), ("verified_update", 5)],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO badge_definitions (badge_key, name, description, contribution_threshold) VALUES (?, ?, ?, ?)",
        [
            ("civic_starter", "Civic Starter", "One eligible, verified contribution.", 1),
            ("responsible_citizen", "Responsible Citizen", "Five eligible, verified contributions.", 5),
            ("community_helper", "Community Helper", "Ten eligible, verified contributions.", 10),
            ("civic_champion", "Civic Champion", "Twenty-five eligible, verified contributions.", 25),
            ("social_impact", "Social Impact", "An administrator-verified qualifying contribution to a significant public issue.", 0),
        ],
    )
    conn.execute("INSERT OR IGNORE INTO reward_settings (setting_key, setting_value) VALUES ('leaderboard_enabled', '0')")
    conn.execute("INSERT OR IGNORE INTO reward_settings (setting_key, setting_value) VALUES ('leaderboard_salt', ?)", (secrets.token_hex(32),))
    conn.commit()
    conn.close()


init_db()


def serialize_user(user_row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": user_row["id"],
        "name": user_row["name"],
        "email": user_row["email"],
        "role": user_row["role"],
        "created_at": user_row["created_at"],
    }


def get_user_by_token(token: str) -> Optional[sqlite3.Row]:
    if not token:
        return None
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE session_token = ?", (token,)).fetchone()
    conn.close()
    return row


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    conn.close()
    return row


def get_complaint_by_id(complaint_id: str) -> Optional[sqlite3.Row]:
    conn = get_db()
    row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
    conn.close()
    return row


def normalize_complaint_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def find_duplicate_complaint(conn: sqlite3.Connection, citizen_id: int, title: str, location: str) -> Optional[sqlite3.Row]:
    normalized_location = normalize_complaint_text(location)
    normalized_title = normalize_complaint_text(title)
    rows = conn.execute(
        "SELECT complaint_id, title, status, location FROM complaints WHERE user_id = ? AND status NOT IN ('Resolved', 'Rejected') ORDER BY created_at DESC",
        (citizen_id,),
    ).fetchall()

    for row in rows:
        if normalize_complaint_text(row["location"] or "") != normalized_location:
            continue
        existing_title = normalize_complaint_text(row["title"])
        if existing_title == normalized_title or SequenceMatcher(None, existing_title, normalized_title).ratio() >= 0.82:
            return row
    return None


def add_history(complaint_id: str, action: str, details: str, changed_by: Optional[int] = None) -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO complaint_history (complaint_id, action, details, changed_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (complaint_id, action, details, changed_by, iso_now()),
    )
    conn.commit()
    conn.close()


def add_audit_log(actor_id: Optional[int], actor_role: Optional[str], complaint_id: Optional[str], action: str, details: str) -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO audit_logs (actor_id, actor_role, complaint_id, action, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (actor_id, actor_role, complaint_id, action, details, iso_now()),
    )
    conn.commit()
    conn.close()


def reward_rule_points(conn: sqlite3.Connection, rule_key: str) -> int:
    row = conn.execute("SELECT points, enabled FROM reward_rules WHERE rule_key = ?", (rule_key,)).fetchone()
    return int(row["points"]) if row and row["enabled"] else 0


def add_reward_transaction(
    conn: sqlite3.Connection,
    citizen_id: int,
    points: int,
    event_type: str,
    event_key: str,
    reason: str,
    authorized_by: Optional[int],
    complaint_id: Optional[str] = None,
    update_id: Optional[int] = None,
    reversal_of: Optional[int] = None,
) -> bool:
    if points == 0:
        return False
    cursor = conn.execute(
        "INSERT OR IGNORE INTO reward_transactions (transaction_id, citizen_id, complaint_id, update_id, event_type, points, reason, event_key, authorized_by, reversal_of, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uuid.uuid4().hex, citizen_id, complaint_id, update_id, event_type, points, reason, event_key, authorized_by, reversal_of, iso_now()),
    )
    return cursor.rowcount == 1


def reverse_reward_transaction(conn: sqlite3.Connection, transaction: sqlite3.Row, admin_id: int, reason: str) -> bool:
    if transaction["reversal_of"] is not None or transaction["points"] < 0:
        return False
    return add_reward_transaction(
        conn,
        transaction["citizen_id"],
        -transaction["points"],
        "reversal",
        f"reversal:{transaction['id']}",
        reason,
        admin_id,
        transaction["complaint_id"],
        transaction["update_id"],
        transaction["id"],
    )


def award_contribution_badges(conn: sqlite3.Connection, citizen_id: int) -> None:
    count = conn.execute(
        "SELECT (SELECT COUNT(*) FROM reward_reviews WHERE citizen_id = ? AND eligible = 1) + (SELECT COUNT(*) FROM complaint_updates WHERE citizen_id = ? AND review_status = 'Verified')",
        (citizen_id, citizen_id),
    ).fetchone()[0]
    badges = conn.execute(
        "SELECT badge_key, name, contribution_threshold FROM badge_definitions WHERE enabled = 1 AND contribution_threshold > 0",
    ).fetchall()
    now = iso_now()
    for badge in badges:
        if count >= badge["contribution_threshold"]:
            conn.execute(
                "INSERT OR IGNORE INTO citizen_badges (citizen_id, badge_key, criteria_satisfied, awarded_at) VALUES (?, ?, ?, ?)",
                (citizen_id, badge["badge_key"], f"{count} verified contributions; threshold {badge['contribution_threshold']}.", now),
            )
        else:
            conn.execute(
                "UPDATE citizen_badges SET revoked_at = ?, revoked_reason = 'Verified contribution count fell below the configured badge threshold.' WHERE citizen_id = ? AND badge_key = ? AND revoked_at IS NULL",
                (now, citizen_id, badge["badge_key"]),
            )


def verified_contribution_count(conn: sqlite3.Connection, citizen_id: int) -> int:
    return conn.execute(
        "SELECT (SELECT COUNT(*) FROM reward_reviews WHERE citizen_id = ? AND eligible = 1) + (SELECT COUNT(*) FROM complaint_updates WHERE citizen_id = ? AND review_status = 'Verified')",
        (citizen_id, citizen_id),
    ).fetchone()[0]


def pseudonym_for_citizen(citizen_id: int, salt: str) -> str:
    digest = hashlib.sha256(f"{salt}:{citizen_id}".encode("utf-8")).hexdigest()[:8].upper()
    return f"Civic Member {digest}"


def predict_grievance(title: str, description: str, category: Optional[str] = None) -> Dict[str, Any]:
    combined = f"{title} {description} {category or ''}".lower()
    candidate_scores = {
        "Water Supply": ["water", "pipe", "leak", "tank", "supply", "pressure", "faucet"],
        "Sanitation": ["garbage", "waste", "bin", "toilet", "sewage", "sanitation", "drainage", "cleaning"],
        "Street Lighting": ["street light", "streetlight", "lamp", "electricity", "power", "lighting", "dark", "bulb"],
        "Roads / Public Works": ["road", "pothole", "lane", "asphalt", "sidewalk", "public works", "repair"],
        "Drainage": ["drain", "overflow", "flood", "waterlogging", "stagnant", "drainage"],
        "Administration": ["portal", "scholarship", "certificate", "document", "fee", "admission", "registration"],
        "Campus Facilities": ["wifi", "hostel", "lift", "classroom", "cooler", "washroom", "fan", "restroom"],
    }

    scores = {}
    for key, terms in candidate_scores.items():
        score = 0
        for term in terms:
            if term in combined:
                score += 1
        scores[key] = score

    if category and category.strip():
        normalized = category.strip()
        if normalized in scores:
            scores[normalized] += 2

    best_category, best_score = max(scores.items(), key=lambda item: item[1], default=("General Review", 0))
    final_category = best_category if best_score > 0 else "General Review"
    final_confidence = min(97, 68 + (best_score * 8)) if best_score > 0 else 42

    danger_keywords = ["danger", "unsafe", "fire", "electrical", "flood", "breach", "collapse", "accident", "severe"]
    urgency_keywords = ["urgent", "immediate", "not working", "broken", "critical", "overflow", "leak", "stagnant"]
    if any(word in combined for word in danger_keywords):
        priority = "Critical"
    elif any(word in combined for word in urgency_keywords):
        priority = "High"
    elif "water" in combined or "garbage" in combined or "road" in combined:
        priority = "Medium"
    else:
        priority = "Low"

    if final_category == "General Review" or final_confidence < 55:
        requires_human_review = True
    else:
        requires_human_review = False

    return {
        "predicted_category": final_category,
        "predicted_priority": priority,
        "confidence": round(final_confidence, 1),
        "recommended_department": CATEGORY_TO_DEPARTMENT.get(final_category, "Administrator Review Queue"),
        "requires_human_review": requires_human_review,
        "model_version": "keyword_fallback_v1",
        "model_note": "Transparent heuristic fallback used because no trained production model is available in the project.",
    }


def calculate_deadline(priority: str) -> str:
    hours = PRIORITY_SLA_HOURS.get(priority, 120)
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_complaint_id() -> str:
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0] + 1
    conn.close()
    return f"GRV-{datetime.now(timezone.utc).year}-{count:04d}"


def serialize_complaint(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["complaint_id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "description": row["description"],
        "category": row["category"],
        "location": row["location"],
        "priority": row["priority"],
        "department": row["department"],
        "status": row["status"],
        "assigned_officer": row["assigned_officer"],
        "evidence": row["evidence"],
        "deadline": row["deadline"],
        "escalation_reason": row["escalation_reason"],
        "resolution": row["resolution"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_complaint_history(complaint_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM complaint_history WHERE complaint_id = ? ORDER BY created_at ASC",
        (complaint_id,),
    ).fetchall()
    conn.close()
    return [{
        "action": row["action"],
        "details": row["details"],
        "created_at": row["created_at"],
    } for row in rows]


def get_ai_prediction(complaint_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    row = conn.execute("SELECT * FROM ai_predictions WHERE complaint_id = ?", (complaint_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "predicted_category": row["predicted_category"],
        "predicted_priority": row["predicted_priority"],
        "confidence": row["confidence"],
        "recommended_department": row["recommended_department"],
        "model_version": row["model_version"],
        "requires_human_review": bool(row["requires_human_review"]),
        "prediction_json": row["prediction_json"],
    }


def current_user_required():
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not token:
        return None
    return get_user_by_token(token)


def require_auth(role: Optional[str] = None):
    user = current_user_required()
    if not user:
        return None, (jsonify({"error": "Authentication required."}), 401)
    if role and user["role"] != role:
        return None, (jsonify({"error": f"{role.title()} access required."}), 403)
    return user, None


def process_overdue_complaints() -> None:
    conn = get_db()
    now = iso_now()
    rows = conn.execute(
        "SELECT * FROM complaints WHERE status NOT IN ('Resolved', 'Rejected', 'Escalated') AND deadline IS NOT NULL AND deadline < ?",
        (now,),
    ).fetchall()
    for row in rows:
        has_active = conn.execute(
            "SELECT 1 FROM escalations WHERE complaint_id = ? AND stage = 'first_escalation' LIMIT 1",
            (row["complaint_id"],),
        ).fetchone()
        if has_active:
            continue

        conn.execute(
            "UPDATE complaints SET status = 'Escalated', escalation_reason = ?, updated_at = ? WHERE complaint_id = ?",
            ("Deadline passed before resolution. Escalated to administrator review queue.", now, row["complaint_id"]),
        )
        conn.execute(
            "INSERT INTO escalations (complaint_id, stage, escalated_to, reason, created_at) VALUES (?, 'first_escalation', 'Administrator Review Queue', ?, ?)",
            (row["complaint_id"], "Deadline passed before resolution. Escalated to administrator review queue.", now),
        )
        conn.execute(
            "INSERT INTO complaint_history (complaint_id, action, details, changed_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                row["complaint_id"],
                "Auto escalated",
                "Complaint exceeded the SLA deadline and was escalated automatically.",
                row["user_id"],
                now,
            ),
        )
        conn.execute(
            "INSERT INTO audit_logs (actor_id, actor_role, complaint_id, action, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (row["user_id"], "system", row["complaint_id"], "auto_escalation", "Complaint exceeded deadline and was escalated.", now),
        )
    conn.commit()
    conn.close()


scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(process_overdue_complaints, "interval", seconds=60)
scheduler.start()


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "resolveai", "timestamp": iso_now()})


@app.route("/api/register", methods=["POST"])
def register():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not name or not email or len(password) < 4:
        return jsonify({"error": "Name, valid email, and password of at least 4 characters are required."}), 400

    if get_user_by_email(email):
        return jsonify({"error": "An account with this email already exists."}), 409

    token = uuid.uuid4().hex
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash, role, session_token, created_at) VALUES (?, ?, ?, 'citizen', ?, ?)",
        (name, email, generate_password_hash(password), token, iso_now()),
    )
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    conn.close()
    return jsonify({"token": token, "user": serialize_user(user)})


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    role = (payload.get("role") or "citizen").strip().lower()

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ? AND role = ?", (email, role)).fetchone()
    conn.close()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials for this role."}), 401

    token = uuid.uuid4().hex
    conn = get_db()
    conn.execute("UPDATE users SET session_token = ? WHERE id = ?", (token, user["id"]))
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    conn.close()
    return jsonify({"token": token, "user": serialize_user(user)})


@app.route("/api/profile")
def profile():
    user, error = require_auth()
    if error:
        return error
    return jsonify({"user": serialize_user(user)})


@app.route("/api/citizen/complaints")
def citizen_complaints():
    user, error = require_auth("citizen")
    if error:
        return error
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    conn.close()
    return jsonify({"complaints": [serialize_complaint(row) for row in rows]})


@app.route("/api/complaints", methods=["POST"])
def submit_complaint():
    user, error = require_auth("citizen")
    if error:
        return error
    payload = request.get_json(silent=True) or request.form
    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    category = (payload.get("category") or "").strip()
    location = (payload.get("location") or "").strip()
    evidence_file = request.files.get("evidence")
    evidence = ""

    if evidence_file and evidence_file.filename:
        filename = secure_filename(evidence_file.filename)
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in ALLOWED_EVIDENCE_EXTENSIONS:
            return jsonify({"error": "Evidence must be an image, PDF, DOC, or DOCX file."}), 400
        evidence = f"{uuid.uuid4().hex}_{filename}"

    if not title or not description or not location:
        return jsonify({"error": "Complaint title, description, and location are required."}), 400

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    duplicate = find_duplicate_complaint(conn, user["id"], title, location)
    if duplicate:
        conn.close()
        return jsonify({
            "error": "A complaint for this problem at this location has already been submitted."
        }), 409

    if evidence_file and evidence:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        evidence_file.save(os.path.join(UPLOAD_FOLDER, evidence))

    prediction = predict_grievance(title, description, category)
    complaint_id = generate_complaint_id()
    deadline = calculate_deadline(prediction["predicted_priority"])
    now = iso_now()
    department = prediction["recommended_department"]
    status = "Pending"

    conn.execute(
        "INSERT INTO complaints (complaint_id, user_id, title, description, category, location, priority, department, status, evidence, deadline, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            complaint_id,
            user["id"],
            title,
            description,
            prediction["predicted_category"],
            location,
            prediction["predicted_priority"],
            department,
            status,
            evidence,
            deadline,
            now,
            now,
        ),
    )
    conn.execute(
        "INSERT INTO ai_predictions (complaint_id, predicted_category, predicted_priority, confidence, recommended_department, model_version, requires_human_review, prediction_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            complaint_id,
            prediction["predicted_category"],
            prediction["predicted_priority"],
            prediction["confidence"],
            prediction["recommended_department"],
            prediction["model_version"],
            int(prediction["requires_human_review"]),
            str(prediction),
            now,
        ),
    )
    conn.commit()
    conn.close()

    add_history(complaint_id, "Complaint submitted", "Complaint created by citizen and queued for review.", user["id"])
    add_audit_log(user["id"], "citizen", complaint_id, "complaint_created", "Citizen submitted a new complaint.")

    complaint = get_complaint_by_id(complaint_id)
    return jsonify({
        "message": "Complaint submitted successfully.",
        "complaint": serialize_complaint(complaint),
        "prediction": get_ai_prediction(complaint_id),
    })


@app.route("/api/complaints/<complaint_id>/evidence")
def complaint_evidence(complaint_id: str):
    user, error = require_auth()
    if error:
        return error

    conn = get_db()
    row = conn.execute(
        "SELECT user_id, evidence FROM complaints WHERE complaint_id = ?",
        (complaint_id,),
    ).fetchone()
    conn.close()
    if not row or not row["evidence"]:
        return jsonify({"error": "Evidence not found."}), 404
    if user["role"] == "citizen" and row["user_id"] != user["id"]:
        return jsonify({"error": "You are not allowed to access this evidence."}), 403

    return send_from_directory(
        UPLOAD_FOLDER,
        os.path.basename(row["evidence"]),
        as_attachment=True,
    )


@app.route("/api/complaints/<complaint_id>")
def complaint_details(complaint_id: str):
    user, error = require_auth()
    if error:
        return error
    conn = get_db()
    row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Complaint not found."}), 404
    if user["role"] == "citizen" and row["user_id"] != user["id"]:
        return jsonify({"error": "You are not allowed to view this complaint."}), 403

    complaint = serialize_complaint(row)
    complaint["history"] = get_complaint_history(complaint_id)
    complaint["prediction"] = get_ai_prediction(complaint_id)
    return jsonify({"complaint": complaint})


@app.route("/api/complaints/<complaint_id>/updates", methods=["POST"])
def submit_complaint_update(complaint_id: str):
    user, error = require_auth("citizen")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    details = (payload.get("details") or "").strip()
    if not 20 <= len(details) <= 2000:
        return jsonify({"error": "An update must contain 20 to 2000 characters of useful new information."}), 400

    conn = get_db()
    complaint = conn.execute(
        "SELECT complaint_id, status FROM complaints WHERE complaint_id = ? AND user_id = ?",
        (complaint_id, user["id"]),
    ).fetchone()
    if not complaint:
        conn.close()
        return jsonify({"error": "Complaint not found."}), 404
    if complaint["status"] in ("Resolved", "Rejected"):
        conn.close()
        return jsonify({"error": "Updates are not accepted for closed complaints."}), 409
    existing_updates = conn.execute(
        "SELECT details FROM complaint_updates WHERE complaint_id = ? AND citizen_id = ?",
        (complaint_id, user["id"]),
    ).fetchall()
    normalized_details = normalize_complaint_text(details)
    if any(normalize_complaint_text(row["details"]) == normalized_details for row in existing_updates):
        conn.close()
        return jsonify({"error": "This update has already been submitted for this complaint."}), 409
    cursor = conn.execute(
        "INSERT INTO complaint_updates (complaint_id, citizen_id, details, created_at) VALUES (?, ?, ?, ?)",
        (complaint_id, user["id"], details, iso_now()),
    )
    update_id = cursor.lastrowid
    conn.commit()
    conn.close()
    add_history(complaint_id, "Citizen update submitted", "A new update was submitted for administrator review.", user["id"])
    return jsonify({"message": "Update submitted for review.", "update_id": update_id}), 201


@app.route("/api/citizen/rewards")
def citizen_rewards():
    user, error = require_auth("citizen")
    if error:
        return error
    conn = get_db()
    citizen_id = user["id"]
    balance = conn.execute(
        "SELECT COALESCE(SUM(points), 0) FROM reward_transactions WHERE citizen_id = ?",
        (citizen_id,),
    ).fetchone()[0]
    verified = verified_contribution_count(conn, citizen_id)
    resolved = conn.execute(
        "SELECT COUNT(*) FROM reward_reviews WHERE citizen_id = ? AND eligible = 1 AND resolution_verified = 1",
        (citizen_id,),
    ).fetchone()[0]
    badge_rows = conn.execute(
        "SELECT d.badge_key, d.name, d.description, d.contribution_threshold, b.awarded_at, b.criteria_satisfied FROM citizen_badges b JOIN badge_definitions d ON d.badge_key = b.badge_key WHERE b.citizen_id = ? AND b.revoked_at IS NULL ORDER BY b.awarded_at",
        (citizen_id,),
    ).fetchall()
    next_badge = conn.execute(
        "SELECT d.badge_key, d.name, d.contribution_threshold FROM badge_definitions d WHERE d.enabled = 1 AND d.contribution_threshold > ? AND d.contribution_threshold > 0 AND NOT EXISTS (SELECT 1 FROM citizen_badges b WHERE b.citizen_id = ? AND b.badge_key = d.badge_key) ORDER BY d.contribution_threshold LIMIT 1",
        (verified, citizen_id),
    ).fetchone()
    transactions = conn.execute(
        "SELECT transaction_id, complaint_id, event_type, points, reason, created_at FROM reward_transactions WHERE citizen_id = ? ORDER BY created_at DESC, id DESC LIMIT 100",
        (citizen_id,),
    ).fetchall()
    leaderboard_enabled = conn.execute(
        "SELECT setting_value FROM reward_settings WHERE setting_key = 'leaderboard_enabled'",
    ).fetchone()[0] == "1"
    conn.close()

    return jsonify({
        "summary": {"available_points": balance, "verified_contributions": verified, "verified_resolutions": resolved},
        "badges": [dict(row) for row in badge_rows],
        "next_badge": ({"badge_key": next_badge["badge_key"], "name": next_badge["name"], "progress": verified, "target": next_badge["contribution_threshold"]} if next_badge else None),
        "transactions": [dict(row) for row in transactions],
        "certificates": [{"badge_key": row["badge_key"], "name": row["name"], "awarded_at": row["awarded_at"]} for row in badge_rows],
        "leaderboard_enabled": leaderboard_enabled,
        "explanation": "CivicPoints are non-monetary recognition. Points never affect complaint urgency, AI predictions, routing, deadlines, or escalation. Only administrator-verified contributions qualify.",
    })


@app.route("/api/citizen/rewards/certificates/<badge_key>")
def citizen_reward_certificate(badge_key: str):
    user, error = require_auth("citizen")
    if error:
        return error
    conn = get_db()
    badge = conn.execute(
        "SELECT d.name, d.description, b.awarded_at, b.criteria_satisfied FROM citizen_badges b JOIN badge_definitions d ON d.badge_key = b.badge_key WHERE b.citizen_id = ? AND b.badge_key = ? AND b.revoked_at IS NULL",
        (user["id"], badge_key),
    ).fetchone()
    conn.close()
    if not badge:
        return jsonify({"error": "Certificate not found."}), 404
    document = f"""<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><title>Civic Impact milestone</title><style>body{{font:18px Georgia,serif;color:#17334a;margin:8vh auto;max-width:760px;text-align:center;border:4px double #17865b;padding:56px}}small{{font:14px Arial,sans-serif;color:#53657a}}h1{{font-size:38px}}h2{{font-size:30px;color:#17865b}}footer{{margin-top:48px}}</style><body><small>CIVIC IMPACT REWARDS · PERSONAL MILESTONE</small><h1>Certificate of Contribution</h1><p>This acknowledges</p><h2>{escape(user['name'])}</h2><p>for earning the <strong>{escape(badge['name'])}</strong> digital badge.</p><p>{escape(badge['criteria_satisfied'])}</p><footer><p>A non-governmental, non-monetary project recognition record.</p><small>Issued {escape(badge['awarded_at'])} · This certificate is not an official government credential.</small></footer></body></html>"""
    response = Response(document, mimetype="text/html")
    response.headers["Content-Disposition"] = f"attachment; filename={badge_key}-civic-impact-certificate.html"
    return response


@app.route("/api/citizen/leaderboard")
def citizen_reward_leaderboard():
    user, error = require_auth("citizen")
    if error:
        return error
    conn = get_db()
    enabled = conn.execute(
        "SELECT setting_value FROM reward_settings WHERE setting_key = 'leaderboard_enabled'",
    ).fetchone()[0] == "1"
    if not enabled:
        conn.close()
        return jsonify({"error": "The community leaderboard is disabled."}), 404
    rows = conn.execute(
        "SELECT u.id AS citizen_id, (SELECT COUNT(*) FROM reward_reviews r WHERE r.citizen_id = u.id AND r.eligible = 1) + (SELECT COUNT(*) FROM complaint_updates x WHERE x.citizen_id = u.id AND x.review_status = 'Verified') AS contributions, (SELECT COUNT(*) FROM reward_reviews r WHERE r.citizen_id = u.id AND r.eligible = 1 AND r.resolution_verified = 1) AS verified_resolutions FROM users u WHERE u.role = 'citizen' AND ((SELECT COUNT(*) FROM reward_reviews r WHERE r.citizen_id = u.id AND r.eligible = 1) + (SELECT COUNT(*) FROM complaint_updates x WHERE x.citizen_id = u.id AND x.review_status = 'Verified')) > 0 ORDER BY verified_resolutions DESC, contributions DESC LIMIT 50"
    ).fetchall()
    salt = conn.execute("SELECT setting_value FROM reward_settings WHERE setting_key = 'leaderboard_salt'").fetchone()[0]
    entries = [{
        "display_name": pseudonym_for_citizen(row["citizen_id"], salt),
        "verified_contributions": row["contributions"],
        "verified_resolutions": row["verified_resolutions"] or 0,
    } for row in rows]
    conn.close()
    return jsonify({"leaderboard": entries})


@app.route("/api/admin/rewards/pending")
def admin_pending_rewards():
    admin, error = require_auth("admin")
    if error:
        return error
    conn = get_db()
    complaints = conn.execute(
        "SELECT c.complaint_id, c.user_id, u.name AS citizen_name, c.title, c.description, c.location, c.status, c.priority, c.department, c.evidence, c.resolution FROM complaints c JOIN users u ON u.id = c.user_id LEFT JOIN reward_reviews r ON r.complaint_id = c.complaint_id WHERE r.complaint_id IS NULL ORDER BY c.created_at DESC"
    ).fetchall()
    all_reports = conn.execute("SELECT complaint_id, title, location FROM complaints").fetchall()
    updates = conn.execute(
        "SELECT x.id, x.complaint_id, x.citizen_id, u.name AS citizen_name, c.title, x.details, x.created_at FROM complaint_updates x JOIN users u ON u.id = x.citizen_id JOIN complaints c ON c.complaint_id = x.complaint_id WHERE x.review_status = 'Pending' ORDER BY x.created_at DESC"
    ).fetchall()
    conn.close()
    complaint_items = []
    for complaint in complaints:
        related_ids = [
            other["complaint_id"] for other in all_reports
            if other["complaint_id"] != complaint["complaint_id"]
            and normalize_complaint_text(other["location"] or "") == normalize_complaint_text(complaint["location"] or "")
            and SequenceMatcher(None, normalize_complaint_text(other["title"]), normalize_complaint_text(complaint["title"])).ratio() >= 0.72
        ]
        item = dict(complaint)
        item["potential_related_reports"] = related_ids
        complaint_items.append(item)
    return jsonify({"complaints": complaint_items, "updates": [dict(row) for row in updates]})


@app.route("/api/admin/rewards/complaints/<complaint_id>/decision", methods=["POST"])
def admin_reward_complaint_decision(complaint_id: str):
    admin, error = require_auth("admin")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    eligible = payload.get("eligible")
    evidence_approved = payload.get("evidence_approved", False)
    resolution_verified = payload.get("resolution_verified", False)
    social_impact = payload.get("social_impact_verified", False)
    reason = (payload.get("reason") or "").strip()
    if not all(isinstance(value, bool) for value in (eligible, evidence_approved, resolution_verified, social_impact)) or not reason:
        return jsonify({"error": "Eligibility decisions and a review reason are required."}), 400

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    complaint = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
    if not complaint:
        conn.close()
        return jsonify({"error": "Complaint not found."}), 404
    if eligible and complaint["status"] == "Rejected":
        conn.close()
        return jsonify({"error": "Rejected complaints cannot be marked reward-eligible."}), 400
    if evidence_approved and (not complaint["evidence"] or not os.path.isfile(os.path.join(UPLOAD_FOLDER, complaint["evidence"]))):
        conn.close()
        return jsonify({"error": "This complaint has no accessible evidence attachment to approve."}), 400
    if resolution_verified and (complaint["status"] != "Resolved" or not complaint["resolution"]):
        conn.close()
        return jsonify({"error": "Resolution rewards require a resolved complaint and documented resolution."}), 400
    if not eligible and (evidence_approved or resolution_verified or social_impact):
        conn.close()
        return jsonify({"error": "An ineligible complaint cannot receive contribution, evidence, resolution, or milestone rewards."}), 400

    conn.execute(
        "INSERT INTO reward_reviews (complaint_id, citizen_id, eligible, evidence_approved, resolution_verified, social_impact_verified, reason, administrator_id, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(complaint_id) DO UPDATE SET eligible=excluded.eligible, evidence_approved=excluded.evidence_approved, resolution_verified=excluded.resolution_verified, social_impact_verified=excluded.social_impact_verified, reason=excluded.reason, administrator_id=excluded.administrator_id, reviewed_at=excluded.reviewed_at",
        (complaint_id, complaint["user_id"], int(eligible), int(evidence_approved), int(resolution_verified), int(social_impact), reason, admin["id"], iso_now()),
    )
    conn.execute(
        "INSERT INTO reward_review_events (complaint_id, citizen_id, eligible, evidence_approved, resolution_verified, social_impact_verified, reason, administrator_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (complaint_id, complaint["user_id"], int(eligible), int(evidence_approved), int(resolution_verified), int(social_impact), reason, admin["id"], iso_now()),
    )
    reward_events = [
        ("verified_contribution", "verified_contribution", eligible, "Eligible public complaint verified."),
        ("evidence_approved", "evidence_approved", eligible and evidence_approved, "Supporting evidence reviewed and approved."),
        ("resolution_verified", "resolution_verified", eligible and resolution_verified, "Complaint resolution verified by an administrator."),
    ]
    for rule, event, should_award, default_reason in reward_events:
        original = conn.execute(
            "SELECT * FROM reward_transactions WHERE event_key = ? AND points > 0",
            (f"complaint:{complaint_id}:{event}",),
        ).fetchone()
        if should_award:
            add_reward_transaction(conn, complaint["user_id"], reward_rule_points(conn, rule), event, f"complaint:{complaint_id}:{event}", f"{default_reason} {reason}", admin["id"], complaint_id)
        elif original:
            reverse_reward_transaction(conn, original, admin["id"], f"Reward eligibility corrected: {reason}")

    if social_impact:
        conn.execute(
            "INSERT OR IGNORE INTO citizen_badges (citizen_id, badge_key, criteria_satisfied, awarded_at) VALUES (?, 'social_impact', ?, ?)",
            (complaint["user_id"], f"{complaint_id}: {reason}", iso_now()),
        )
    else:
        conn.execute(
            "UPDATE citizen_badges SET revoked_at = ?, revoked_reason = ? WHERE citizen_id = ? AND badge_key = 'social_impact' AND revoked_at IS NULL AND criteria_satisfied LIKE ?",
            (iso_now(), reason, complaint["user_id"], f"{complaint_id}: %"),
        )
    award_contribution_badges(conn, complaint["user_id"])
    conn.commit()
    conn.close()
    add_audit_log(admin["id"], "admin", complaint_id, "reward_review", reason)
    return jsonify({"message": "Reward eligibility review recorded."})


@app.route("/api/admin/rewards/updates/<int:update_id>/decision", methods=["POST"])
def admin_reward_update_decision(update_id: int):
    admin, error = require_auth("admin")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    verified = payload.get("verified")
    reason = (payload.get("reason") or "").strip()
    if not isinstance(verified, bool) or not reason:
        return jsonify({"error": "A verification decision and reason are required."}), 400

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    update = conn.execute("SELECT * FROM complaint_updates WHERE id = ?", (update_id,)).fetchone()
    if not update:
        conn.close()
        return jsonify({"error": "Contribution update not found."}), 404
    conn.execute(
        "UPDATE complaint_updates SET review_status = ?, review_reason = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
        ("Verified" if verified else "Rejected", reason, admin["id"], iso_now(), update_id),
    )
    event_key = f"update:{update_id}:verified_update"
    original = conn.execute("SELECT * FROM reward_transactions WHERE event_key = ? AND points > 0", (event_key,)).fetchone()
    if verified:
        add_reward_transaction(conn, update["citizen_id"], reward_rule_points(conn, "verified_update"), "verified_update", event_key, f"Administrator verified a useful new issue update. {reason}", admin["id"], update["complaint_id"], update_id)
    elif original:
        reverse_reward_transaction(conn, original, admin["id"], f"Verified update eligibility corrected: {reason}")
    conn.commit()
    conn.close()
    add_history(update["complaint_id"], "Citizen update reviewed", reason, admin["id"])
    add_audit_log(admin["id"], "admin", update["complaint_id"], "reward_update_review", reason)
    return jsonify({"message": "Contribution update review recorded."})


@app.route("/api/admin/rewards/adjustments", methods=["POST"])
def admin_reward_adjustment():
    admin, error = require_auth("admin")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    citizen_id = payload.get("citizen_id")
    points = payload.get("points")
    reason = (payload.get("reason") or "").strip()
    complaint_id = (payload.get("complaint_id") or "").strip() or None
    idempotency_key = (payload.get("idempotency_key") or "").strip()
    if not isinstance(citizen_id, int) or not isinstance(points, int) or points == 0 or abs(points) > 1000 or len(reason) < 8 or not 8 <= len(idempotency_key) <= 100:
        return jsonify({"error": "Citizen ID, a non-zero adjustment up to 1000 points, a reason of at least 8 characters, and an idempotency key are required."}), 400

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    if not conn.execute("SELECT 1 FROM users WHERE id = ? AND role = 'citizen'", (citizen_id,)).fetchone():
        conn.close()
        return jsonify({"error": "Citizen not found."}), 404
    if complaint_id and not conn.execute("SELECT 1 FROM complaints WHERE complaint_id = ? AND user_id = ?", (complaint_id, citizen_id)).fetchone():
        conn.close()
        return jsonify({"error": "Complaint not found for this citizen."}), 404
    current_balance = conn.execute("SELECT COALESCE(SUM(points), 0) FROM reward_transactions WHERE citizen_id = ?", (citizen_id,)).fetchone()[0]
    if current_balance + points < 0:
        conn.close()
        return jsonify({"error": "An adjustment cannot reduce the CivicPoints balance below zero."}), 400
    inserted = add_reward_transaction(conn, citizen_id, points, "admin_adjustment", f"adjustment:{admin['id']}:{idempotency_key}", reason, admin["id"], complaint_id)
    conn.commit()
    conn.close()
    if not inserted:
        return jsonify({"error": "This adjustment request was already recorded."}), 409
    add_audit_log(admin["id"], "admin", complaint_id, "reward_adjustment", f"Citizen {citizen_id}: {points:+d} CivicPoints. {reason}")
    return jsonify({"message": "Auditable reward adjustment recorded."}), 201


@app.route("/api/admin/rewards/transactions/<transaction_id>/reverse", methods=["POST"])
def admin_reverse_reward(transaction_id: str):
    admin, error = require_auth("admin")
    if error:
        return error
    reason = ((request.get_json(silent=True) or {}).get("reason") or "").strip()
    if len(reason) < 8:
        return jsonify({"error": "A reason of at least 8 characters is required."}), 400
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    transaction = conn.execute("SELECT * FROM reward_transactions WHERE transaction_id = ?", (transaction_id,)).fetchone()
    if not transaction:
        conn.close()
        return jsonify({"error": "Reward transaction not found."}), 404
    reversed = reverse_reward_transaction(conn, transaction, admin["id"], reason)
    if not reversed:
        conn.close()
        return jsonify({"error": "This transaction cannot be reversed or has already been reversed."}), 409
    conn.commit()
    conn.close()
    add_audit_log(admin["id"], "admin", transaction["complaint_id"], "reward_reversal", f"Transaction {transaction_id} reversed. {reason}")
    return jsonify({"message": "Auditable reversal transaction recorded."})


@app.route("/api/admin/rewards/config", methods=["GET", "PATCH"])
def admin_reward_config():
    admin, error = require_auth("admin")
    if error:
        return error
    conn = get_db()
    if request.method == "PATCH":
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload.get("rules", {}), dict) or not isinstance(payload.get("badges", {}), dict):
            conn.close()
            return jsonify({"error": "Rules and badges must be JSON objects."}), 400
        try:
            conn.execute("BEGIN IMMEDIATE")
            for key, value in (payload.get("rules") or {}).items():
                if key not in {"verified_contribution", "evidence_approved", "resolution_verified", "verified_update"}:
                    raise ValueError("Unknown reward rule.")
                points = value.get("points")
                enabled = value.get("enabled")
                if not isinstance(points, int) or not 0 <= points <= 1000 or not isinstance(enabled, bool):
                    raise ValueError("Rule points must be between 0 and 1000 and enabled must be boolean.")
                conn.execute("UPDATE reward_rules SET points = ?, enabled = ? WHERE rule_key = ?", (points, int(enabled), key))
            for key, threshold in (payload.get("badges") or {}).items():
                if not isinstance(threshold, int) or not 1 <= threshold <= 10000:
                    raise ValueError("Badge thresholds must be between 1 and 10000.")
                changed = conn.execute("UPDATE badge_definitions SET contribution_threshold = ? WHERE badge_key = ? AND badge_key != 'social_impact'", (threshold, key))
                if not changed.rowcount:
                    raise ValueError("Unknown or non-configurable badge.")
            if "leaderboard_enabled" in payload:
                if not isinstance(payload["leaderboard_enabled"], bool):
                    raise ValueError("Leaderboard setting must be boolean.")
                conn.execute("UPDATE reward_settings SET setting_value = ? WHERE setting_key = 'leaderboard_enabled'", ("1" if payload["leaderboard_enabled"] else "0",))
            for citizen in conn.execute("SELECT id FROM users WHERE role = 'citizen'").fetchall():
                award_contribution_badges(conn, citizen["id"])
            conn.commit()
        except (TypeError, ValueError) as exc:
            conn.rollback()
            conn.close()
            return jsonify({"error": str(exc)}), 400
        add_audit_log(admin["id"], "admin", None, "reward_config_updated", "Administrator updated Civic Impact Rewards configuration.")

    rules = conn.execute("SELECT rule_key, points, enabled FROM reward_rules ORDER BY rule_key").fetchall()
    badges = conn.execute("SELECT badge_key, name, description, contribution_threshold, enabled FROM badge_definitions ORDER BY contribution_threshold, name").fetchall()
    leaderboard_enabled = conn.execute("SELECT setting_value FROM reward_settings WHERE setting_key = 'leaderboard_enabled'").fetchone()[0] == "1"
    conn.close()
    return jsonify({"rules": [dict(row) for row in rules], "badges": [dict(row) for row in badges], "leaderboard_enabled": leaderboard_enabled})


@app.route("/api/admin/rewards/transactions")
def admin_reward_transactions():
    admin, error = require_auth("admin")
    if error:
        return error
    conn = get_db()
    rows = conn.execute(
        "SELECT t.transaction_id, t.citizen_id, u.name AS citizen_name, t.complaint_id, t.update_id, t.event_type, t.points, t.reason, t.authorized_by, t.reversal_of, t.created_at FROM reward_transactions t JOIN users u ON u.id = t.citizen_id ORDER BY t.created_at DESC, t.id DESC LIMIT 250"
    ).fetchall()
    conn.close()
    return jsonify({"transactions": [dict(row) for row in rows]})


@app.route("/api/admin/rewards/stats")
def admin_reward_stats():
    admin, error = require_auth("admin")
    if error:
        return error
    conn = get_db()
    pending_complaints = conn.execute("SELECT COUNT(*) FROM complaints c LEFT JOIN reward_reviews r ON r.complaint_id = c.complaint_id WHERE r.complaint_id IS NULL").fetchone()[0]
    pending_updates = conn.execute("SELECT COUNT(*) FROM complaint_updates WHERE review_status = 'Pending'").fetchone()[0]
    stats = {
        "net_points_awarded": conn.execute("SELECT COALESCE(SUM(points), 0) FROM reward_transactions").fetchone()[0],
        "verified_contributions": conn.execute("SELECT (SELECT COUNT(*) FROM reward_reviews WHERE eligible = 1) + (SELECT COUNT(*) FROM complaint_updates WHERE review_status = 'Verified')").fetchone()[0],
        "verified_resolutions": conn.execute("SELECT COUNT(*) FROM reward_reviews WHERE eligible = 1 AND resolution_verified = 1").fetchone()[0],
        "citizens_with_points": conn.execute("SELECT COUNT(DISTINCT citizen_id) FROM reward_transactions WHERE points > 0").fetchone()[0],
        "badges_awarded": conn.execute("SELECT COUNT(*) FROM citizen_badges WHERE revoked_at IS NULL").fetchone()[0],
        "pending_complaints": pending_complaints,
        "pending_updates": pending_updates,
    }
    conn.close()
    return jsonify({"stats": stats})


@app.route("/api/admin/dashboard")
def admin_dashboard():
    user, error = require_auth("admin")
    if error:
        return error
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM complaints WHERE status = 'Pending'").fetchone()[0]
    progress = conn.execute("SELECT COUNT(*) FROM complaints WHERE status = 'In Progress'").fetchone()[0]
    resolved = conn.execute("SELECT COUNT(*) FROM complaints WHERE status = 'Resolved'").fetchone()[0]
    escalated = conn.execute("SELECT COUNT(*) FROM complaints WHERE status = 'Escalated'").fetchone()[0]
    overdue = conn.execute("SELECT COUNT(*) FROM complaints WHERE status NOT IN ('Resolved', 'Rejected') AND deadline < ?", (iso_now(),)).fetchone()[0]
    counts_by_department = conn.execute("SELECT department, COUNT(*) as total FROM complaints GROUP BY department ORDER BY total DESC").fetchall()
    counts_by_priority = conn.execute("SELECT priority, COUNT(*) as total FROM complaints GROUP BY priority ORDER BY total DESC").fetchall()
    conn.close()
    return jsonify({
        "stats": {
            "total": total,
            "new": pending,
            "pending": pending,
            "in_progress": progress,
            "resolved": resolved,
            "overdue": overdue,
            "escalated": escalated,
        },
        "by_department": [{"department": row["department"], "count": row["total"]} for row in counts_by_department],
        "by_priority": [{"priority": row["priority"], "count": row["total"]} for row in counts_by_priority],
    })


@app.route("/api/admin/complaints")
def admin_complaints():
    user, error = require_auth("admin")
    if error:
        return error
    conn = get_db()
    rows = conn.execute("SELECT * FROM complaints ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify({"complaints": [serialize_complaint(row) for row in rows]})


@app.route("/api/admin/complaints/<complaint_id>", methods=["PATCH"])
def update_complaint(complaint_id: str):
    user, error = require_auth("admin")
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    status = (payload.get("status") or "").strip()
    department = (payload.get("department") or "").strip()
    priority = (payload.get("priority") or "").strip()
    assigned_officer = (payload.get("assigned_officer") or "").strip()
    deadline = (payload.get("deadline") or "").strip()
    resolution = (payload.get("resolution") or "").strip()
    escalation_reason = (payload.get("escalation_reason") or "").strip()
    reason = (payload.get("reason") or "").strip() or "Administrative review updated."

    conn = get_db()
    row = conn.execute("SELECT * FROM complaints WHERE complaint_id = ?", (complaint_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Complaint not found."}), 404

    update_fields = ["updated_at = ?"]
    params: List[Any] = [iso_now()]
    if status:
        update_fields.append("status = ?")
        params.append(status)
    if department:
        update_fields.append("department = ?")
        params.append(department)
    if priority:
        update_fields.append("priority = ?")
        params.append(priority)
    if assigned_officer:
        update_fields.append("assigned_officer = ?")
        params.append(assigned_officer)
    if deadline:
        update_fields.append("deadline = ?")
        params.append(deadline)
    if resolution:
        update_fields.append("resolution = ?")
        params.append(resolution)
    if escalation_reason:
        update_fields.append("escalation_reason = ?")
        params.append(escalation_reason)

    params.append(complaint_id)
    conn.execute(f"UPDATE complaints SET {', '.join(update_fields)} WHERE complaint_id = ?", params)
    conn.commit()
    conn.close()

    if status:
        add_history(complaint_id, "Status updated", f"Status changed to {status}. Reason: {reason}", user["id"])
    if department:
        add_history(complaint_id, "Department updated", f"Assigned department to {department}. Reason: {reason}", user["id"])
    if priority:
        add_history(complaint_id, "Priority updated", f"Priority changed to {priority}. Reason: {reason}", user["id"])
    if assigned_officer:
        add_history(complaint_id, "Officer assigned", f"Assigned complaint to {assigned_officer}. Reason: {reason}", user["id"])
    if deadline:
        add_history(complaint_id, "Deadline updated", f"Deadline changed to {deadline}. Reason: {reason}", user["id"])
    if resolution:
        add_history(complaint_id, "Resolution added", resolution, user["id"])
    add_audit_log(user["id"], "admin", complaint_id, "complaint_updated", reason)

    updated = get_complaint_by_id(complaint_id)
    return jsonify({"message": "Complaint updated successfully.", "complaint": serialize_complaint(updated)})


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename: str):
    if filename.startswith("api/"):
        return jsonify({"error": "Not found."}), 404
    if os.path.exists(os.path.join(BASE_DIR, filename)):
        return send_from_directory(BASE_DIR, filename)
    return jsonify({"error": "Not found."}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
