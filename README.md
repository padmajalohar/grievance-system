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

Open two PowerShell terminals in the project directory. In the first:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

In the second:

```powershell
py -m http.server 8000
```

Open <http://localhost:8000>. The Flask API runs on <http://localhost:5001>.

## Test

With the virtual environment active:

```powershell
python -m unittest -v test_app.py
```

The tests cover registration/login, citizen access control, complaint submission and duplicate blocking, protected evidence uploads, administrator updates, overdue escalation, and Civic Impact Rewards verification, privacy, idempotency, badges, and reversals.

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
- Evidence uploads are limited to 8 MB and accepted image/PDF/Word extensions. Files are stored in the local `uploads` directory and served only through the authenticated complaint evidence endpoint.
- Rewards are non-monetary prototype recognition only. No discounts, coupons, cash, or external benefits are available.
