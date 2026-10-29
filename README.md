# ResolveAI Grievance Redressal Prototype

A local Flask and SQLite prototype for citizen complaint intake, heuristic AI classification, SLA tracking, escalation, and administrator review.

## Requirements

- Python 3.11 or newer
- Windows PowerShell (commands below use the Windows Python launcher)

## Setup

From the project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create an administrator account once per database:

```powershell
python create_admin.py --email admin@example.test --password "Use-a-unique-strong-password" --name "System Administrator"
```

The password is supplied locally to the provisioning command; do not reuse a real account password.

## Run

From the project directory, start Flask:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

Open the application directly from Flask:

- Homepage: <http://localhost:5001/>
- Sign in: <http://localhost:5001/login.html>
- Admin dashboard: <http://localhost:5001/admin.html>
- Department staff dashboard: <http://localhost:5001/department.html>

Flask serves both the frontend and API on port 5001. Do not use port 8000 unless you separately start a static file server there; another application may already be using it.

## Interface languages

The interface supports English, Marathi, Hindi, Kannada, and Telugu. Choose a language from the selector in the top-right header area; the choice is stored in this browser and reused across pages. Complaint text and the language preference are not sent to an external translation service or stored as a new database field.

The complaint classifier remains an English keyword heuristic, not a multilingual model. Complaints containing Devanagari, Kannada, or Telugu script are stored as submitted and sent to the administrator review queue without a category or priority prediction. A neutral Medium SLA priority is used until a human assesses the complaint.

## Test

With the virtual environment active:

```powershell
python -m unittest -v test_app.py
python -m unittest -v test_department_demo_seed.py
node test_i18n.js
node test_department.js
node test_auth.js
```

The Flask tests cover registration/login, citizen access control, complaint submission and duplicate blocking, protected evidence uploads, administrator updates, overdue escalation, department staff provisioning and authorization, Civic Impact Rewards verification, privacy, idempotency, badges, reversals, and unsupported-language review handling. The seeder tests use a disposable SQLite database and verify opt-in behavior, repeatability, and preservation of existing rows. The Node tests check language dictionary coverage, fallback behavior, persistence, switching, translated DOM text, department dashboard filters and metrics, and role-based login redirects through same-origin APIs.

## Department staff workflow

Administrators create departments and department staff accounts in the **Department staff accounts** section of `admin.html`. Staff are not publicly self-registered: `/api/register` only creates citizen accounts and rejects non-citizen role requests. When **Department Staff** is selected on the shared sign-in page, the citizen registration link is replaced with instructions to request an administrator-created account. An account is tied to a valid database department and must use a password of at least 12 characters. Administrators can disable an account; this revokes its active token. Staff use the shared sign-in page by selecting **Department Staff**, then open <http://localhost:5001/department.html>.

The department API returns only complaints whose assigned department matches the staff account. Staff can move complaints from Pending or Escalated to In Progress, then from In Progress to Resolved; resolution notes are required to resolve. The dashboard reports totals by priority and status from database values. Department changes, priority changes, rejections, and reopening remain administrator-controlled. These operations are checked on the Flask backend.

The role database change is additive: `departments` and `department_staff_accounts` are created with `CREATE TABLE IF NOT EXISTS`; the existing `users` role constraint and user/complaint records are not rebuilt. A nullable `session_expires_at` field is added to existing users to expire bearer sessions after 12 hours; active legacy sessions receive a 12-hour grace period when this migration first runs. Existing complaint department values are retained and added to the department directory. Departments are not deleted or renamed, so historical assignments are not silently rewritten.

## Database and role permissions

SQLite is accessed through parameterized queries in `app.py`. `complaints.user_id` refers to `users.id`; complaint history and AI predictions refer to complaint IDs. Department staff credentials are stored separately in `department_staff_accounts`, whose `department_id` references the canonical `departments` table. This avoids rebuilding the legacy `users.role` constraint, which accepts only citizens and admins. Staff accounts are created only by administrators, and their department scope is checked by the API for complaint lists, details, evidence, and updates. Existing citizens and administrators keep their current role and password hashes.

No environment variables are required for the local prototype; database, host, port, and upload paths are currently configured in `app.py`. The production server, CORS policy, and secret/session configuration must be hardened before deployment.

## Demonstration scenario

1. Register as a citizen and submit a complaint.
2. Sign in as an administrator, review the recommended route, and assign the complaint to its responsible department.
3. In the staff-management panel, create an account for that department.
4. Sign in using the shared login page with **Department Staff** selected. Confirm the dashboard only shows that department's complaints.
5. Move the complaint to In Progress, add resolution notes, and mark it Resolved.
6. Sign back in as the citizen and review the complaint status and history.

For an optional dashboard demonstration, `seed_department_demo_data.py` appends clearly labelled synthetic complaint rows for every existing department, priority, and supported status. It links them to an existing administrator and does not create or change user rows, credentials, or existing complaint rows. First inspect the plan with `python seed_department_demo_data.py` (read-only dry run); to explicitly insert into the configured database, run `python seed_department_demo_data.py --confirm`. The script is never run automatically, and rerunning it skips deterministic IDs already present. Do not run `--confirm` against a database where synthetic demo rows are not wanted.

## Civic Impact Rewards Demo

The citizen **My grievances** page includes Civic Impact Rewards, sourced from the signed-in citizen's reward ledger. A submitted complaint begins with zero points. An administrator must verify it from the Civic Impact Rewards Management section on `admin.html` before the configured contribution award is recorded. Evidence points require an uploaded, accessible file and explicit admin approval. Resolution points require complaint status `Resolved`, a documented resolution, and explicit admin verification. Citizens can submit a useful-information update from an open complaint's detail modal; administrators verify or reject updates in the rewards queue.

The default configurable rules are 10 points per verified contribution, 5 for approved evidence, 20 for a verified resolution, and 5 per verified useful update. Contribution badges start at 1, 5, 10, and 25 verified contributions. These are stored in SQLite and can be adjusted by administrators from the rewards policy controls. A social-impact badge needs explicit administrator approval. Downloadable milestone certificates are personal HTML records and clearly state that they are not government credentials.

The community leaderboard is disabled by default. An administrator can enable it in reward policy. When enabled, it ranks verified resolutions and verified contributions using stable pseudonyms generated with a random database-local secret; it does not expose email, citizen IDs, or complaint descriptions.

Reward database tables (`reward_rules`, `reward_settings`, `reward_reviews`, `reward_review_events`, `complaint_updates`, `reward_transactions`, `badge_definitions`, and `citizen_badges`) are created additively by `init_db()` using `CREATE TABLE IF NOT EXISTS` and seeded with `INSERT OR IGNORE`. `reward_settings` also stores the leaderboard flag and a generated pseudonym salt. No existing complaint or user table is dropped or reset. Back up `grievance.db` before deployment as with any persistent-data schema change.

Reward APIs:

- `GET /api/citizen/rewards` returns the authenticated citizen's balance, verified contributions/resolutions, badges, progress, certificates, and private ledger.
- `GET /api/citizen/leaderboard` returns pseudonymous rankings only when enabled.
- `GET /api/citizen/rewards/certificates/<badge_key>` downloads an earned personal milestone certificate.
- `POST /api/complaints/<complaint_id>/updates` submits a new 20-2000 character citizen contribution for review.
- `GET /api/admin/rewards/pending` returns complaint and update review queues.
- `POST /api/admin/rewards/complaints/<complaint_id>/decision` records eligibility/evidence/resolution/social-impact decisions.
- `POST /api/admin/rewards/updates/<update_id>/decision` verifies or rejects useful updates.
- `POST /api/admin/rewards/adjustments` records an attributed, idempotent manual adjustment; retries must reuse the same `idempotency_key`.
- `POST /api/admin/rewards/transactions/<transaction_id>/reverse` appends a one-time compensating transaction.
- `GET`/`PATCH /api/admin/rewards/config` reads or changes reward points, badge thresholds, and leaderboard availability.
- `GET /api/admin/rewards/transactions` and `GET /api/admin/rewards/stats` expose administrator-only ledger and summaries.

All points are derived from append-only ledger entries; a database unique event key prevents duplicate awards. Reversals are separate negative transactions and preserve prior entries. Reward decisions never modify AI predictions, complaint priority, department routing, deadlines, or escalation. Independent reports by different citizens are preserved; the admin review queue may flag related reports, but the flag does not reject or merge them.

## Prototype Notes

- Complaint classification is currently a transparent keyword heuristic, not a trained production AI model. Review predicted categories and priorities before operational use.
- The development server, wildcard API CORS configuration, local token storage, and SQLite database are for a local demo only. Deployments handling real citizen information need production-grade hosting, secret/session management, access policies, backups, and privacy controls.
- Bearer sessions are stored in SQLite and logout revokes the active token. There is no automatic session-expiration policy or login rate limiting yet; configure production session management and abuse protections before deployment.
- The application currently runs Flask's development server with debug enabled in `app.py`; never expose that server to the public internet.
- Evidence uploads are limited to 8 MB and accepted image/PDF/Word extensions. Files are stored in the local `uploads` directory and served only through the authenticated complaint evidence endpoint.
- Rewards are non-monetary prototype recognition only. No discounts, coupons, cash, or external benefits are available.
