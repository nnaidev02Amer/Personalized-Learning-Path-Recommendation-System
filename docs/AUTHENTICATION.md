# Authentication, roles and migrations

This document describes how sign-in, authorisation and database migrations work. It applies to the
`feature/auth` work; the API reference is `docs/API.md`.

> **Scope.** This is a local/demo-grade implementation of standard practices (hashed passwords, server-side
> sessions, CSRF protection, role checks). It has **not** had an independent security review. Read the
> [limitations](#known-limitations) before exposing it beyond your own machine.

## Roles

| Role | Can |
|---|---|
| **Administrator** | Everything: list/create/delete students, create logins (new or for an existing seeded student), reset passwords, disable accounts, sign users out, create/edit/archive/delete courses, view every student's enrolments, progress and ML outputs, open Model Evaluation, retrain the models. |
| **Student** | Browse the catalogue, enrol in several courses, see and change **only their own** profile, enrolments, progress, quiz history, ML outputs (skills, difficulty, predictions, recommendations, course guidance) and recommendation history. Cannot list other students, cannot delete anyone (not even themself), cannot open Model Evaluation. |

A student asking for another student's record gets the same `404 not found` as for a non-existent id, so ids cannot be probed.

## The single administrator

There is **exactly one** administrator. It is created only from the command line (no public admin registration, no
role field accepted by any API), and the database itself refuses a second one (partial unique index
`uq_single_admin` on `users(role) WHERE role = 'admin'`). `create_admin` for a different e-mail is refused while an
administrator exists; `--reset-password` changes the password of the existing one.

There is **no default account and no default password**. A fresh database has no users until you create one:

```powershell
.\.venv\Scripts\python.exe -m backend.app.create_admin --email you@example.com --generate-password   # prints a strong password once
.\.venv\Scripts\python.exe -m backend.app.create_admin --email you@example.com                        # or type your own
```

The administrator signs in on the separate **Admin login** page (`/admin/login`); the student page refuses an
administrator account and the admin page refuses a student account.

### Removing all accounts (with a backup)

```powershell
.\.venv\Scripts\python.exe -m backend.app.reset_users            # dry run
.\.venv\Scripts\python.exe -m backend.app.reset_users --apply    # verified backup in dataackups\, then remove
```

Removes every login and session and the learner profiles that belonged to registered/demo logins; keeps courses,
lessons, quizzes and the generated sample learners the ML models train on.

The password is typed at a hidden prompt (twice). For scripts, `--password-stdin` reads one line from standard input.
`--reset-password` changes an existing administrator's password (also the recovery path if you are locked out).
Passwords must be 10-128 characters, not a common password, and must not contain the account's name or e-mail.

Students register themselves (see below) or are created by the administrator (Accounts page, `POST /api/admin/users`).

## Course access: lock, unlock, hide

The administrator controls each course (Courses page, `PATCH /api/courses/{id}`):

* **Lock / Unlock** (`is_locked`) - an *unlocked* course can be joined directly by any student; a *locked* course needs
  approval. Courses that existed before this feature stay locked. New courses are unlocked unless created with `is_locked`.
* **Hide / Unhide** (`is_active`) - a hidden course disappears from the student catalogue and from recommendations; students
  already enrolled keep it and their progress.
* **Create** and **Delete** (only a course nobody has used; otherwise hide it so progress is never lost).
Only the administrator can do any of this.

## Enrolment requests (locked courses)

Students can browse the catalogue and join unlocked courses directly, but **a locked course cannot be joined directly**
(`POST /api/students/{id}/enrollments` answers `403 approval_required`). Instead:

1. the student sends a request (`POST /api/students/{id}/enrollment-requests`) - prerequisites, archived courses and
   duplicates are checked immediately;
2. the administrator approves or rejects it (Enrollment requests page, `POST /api/admin/enrollment-requests/{id}/approve|reject`);
3. only an approval creates the real enrolment, so pending/rejected requests never reach the learning data or the ML models.

Quizzes and lesson progress require an active enrolment, so a course is only studied after approval.

## Self-registration

`ALLOW_SELF_REGISTRATION` is **`true` by default** (set it to `false` to close sign-up). Any number of students can register;
an administrator can never be created this way. When `true`, `POST /api/auth/register` and the Register page
create a **new** student profile together with its login and sign the person in. There is no way to name an
existing student id: the request schema rejects unknown fields, and the server always creates a fresh profile.
Only an administrator can attach a login to an existing (for example seeded) student:
`POST /api/admin/students/{id}/account` (the login e-mail is the profile's e-mail).
Registration is rate limited (10 per hour per address). Keep it off in production unless you need it.

## Sessions

* On login the server creates a random 256-bit token and sets it as the `plrs_session` cookie:
  **`HttpOnly`**, **`SameSite=Lax`**, `Path=/`, `Max-Age` = `SESSION_TTL_HOURS` (default 8), and **`Secure`** when
  `APP_ENV=production` (or `COOKIE_SECURE=true`).
* The database stores only the **SHA-256 hash** of the token (`auth_sessions`), never the token itself.
* Sessions expire (fixed lifetime) and are revoked by logout, by an administrator ("Sign out"), by a password
  reset, and by disabling the account.
* Passwords are hashed with **Argon2id** (`argon2-cffi`). Plain passwords are never stored or logged.

## CSRF and origin checks

* Every state-changing request (POST/PUT/PATCH/DELETE) on an authenticated route must send the session's CSRF
  token in the `X-CSRF-Token` header. The token is returned by `POST /api/auth/login`, `POST /api/auth/register`
  and `GET /api/auth/me`; the web app keeps it in memory only. A token from a different session is rejected.
* If a request carries an `Origin` header it must be one of `CORS_ORIGINS` (or the server's own host), otherwise
  `403 origin_not_allowed`. This also applies to the login and register requests.
* CORS uses an explicit list of origins with credentials. A wildcard (`*`) is refused at start-up.

## Brute-force protection

* **Rate limit** (in process memory): 30 login attempts per minute per client address and 10 per 15 minutes per
  e-mail (existing or not - unknown e-mails are throttled identically).
* **Account lockout** (stored in the database): `MAX_FAILED_LOGINS` (5) consecutive failures lock the account for
  `LOCKOUT_MINUTES` (15). An administrator can unlock it from the Accounts page.
* Wrong password, unknown e-mail and disabled account all return the same `401 invalid_credentials` message.

The limiter counters live in one process, which matches the supported single-worker `uvicorn` deployment. With
several workers or servers they would not be shared; put a reverse proxy / shared store in front for that.
Lockout is in the database and works across workers.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `APP_ENV` | `development` | `production` turns on `Secure` cookies |
| `ALLOW_SELF_REGISTRATION` | `true` | Public student sign-up (never creates an administrator) |
| `SESSION_TTL_HOURS` | `8` | Session lifetime |
| `COOKIE_SECURE` | (from `APP_ENV`) | Force the `Secure` cookie flag on/off |
| `MAX_FAILED_LOGINS` | `5` | Failures before lockout |
| `LOCKOUT_MINUTES` | `15` | Lockout length |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed browser origins (explicit, no `*`) |

No secret has to be configured: session tokens are random and stored hashed, so there is no signing key to leak.
`.env` is git-ignored.

## Production notes

Serve the app over **HTTPS** (a reverse proxy such as Caddy/nginx) with `APP_ENV=production` so cookies are `Secure`,
set `CORS_ORIGINS` to the real front-end origin, and set `ALLOW_SELF_REGISTRATION=false` if you do not want public sign-up. If the front
end and API are on different sites, `SameSite=Lax` cookies will not be sent on cross-site `fetch` calls - serve both
from one origin (reverse proxy `/api`) as the Vite dev proxy does.

## Database schema and migrations

New tables (all additive):

| Table | Purpose |
|---|---|
| `users` | Login accounts: `email`, `password_hash`, `role` (`admin`/`student`), `is_active`, `student_id` (unique FK to `students`, `ON DELETE CASCADE`), lockout fields, timestamps |
| `auth_sessions` | `user_id`, `token_hash` (unique), `csrf_token`, `expires_at`, `revoked_at` |
| `enrollment_requests` | `student_id`, `course_id`, `status` (`pending`/`approved`/`rejected`/`cancelled`), admin `note`, `requested_at`, `decided_at`, `decided_by` (migration `0003`) |
| `recommendation_history` | Per student (and optional course): method, the recommended items, model training time. A row is added only when the list changes |

and one new column, `courses.is_active` (default 1: every existing course stays active; archived courses are hidden from the catalogue and never recommended, but keep their enrolments).

```
users ──0..1── students ──< enrollments >── courses (is_active)
  │                │  └──< quiz_attempts >── quizzes ──< quiz_questions
  └──< auth_sessions   ├──< activity_logs
                       └──< recommendation_history >── courses (optional)
```

One login per student profile (`users.student_id` is unique). Deleting a student deletes their login and sessions.

### How the database is upgraded

Migrations use **Alembic** (`backend/migrations`). Revision `0001` is the frozen pre-authentication schema (the baseline);
`0002` adds the tables above. The application **never migrates an existing database by itself**:

| Database at start-up | Behaviour |
|---|---|
| empty / new | tables are created and the database is stamped at the latest revision |
| already at the latest revision | used as is |
| pre-authentication (never versioned) or older | start-up **stops with a clear message** and changes nothing |

To upgrade an existing database (for example your current `data/app.db`):

```powershell
# 1. Rehearse on a temporary copy - changes nothing, prints row counts before/after
.\.venv\Scripts\python.exe -m backend.app.migrate --dry-run
# 2. Stop the backend, then migrate (makes data\app.db.pre-migration-<timestamp>.bak first, asks for confirmation)
.\.venv\Scripts\python.exe -m backend.app.migrate
```

The command stamps the baseline (no DDL for existing tables), applies `0002`, then verifies that every existing table
kept exactly the same number of rows and that `PRAGMA integrity_check` / `foreign_key_check` pass. Nothing is deleted
or rewritten. To undo, stop the backend and copy the `.bak` file back over the database. Seeded students get no login
until an administrator creates one (Students page -> "Login"). Migrations are tested on SQLite.

## Machine learning and data scoping

The ML methodology is unchanged: BKT, the ability-anchored score model, the LinUCB bandit and the hybrid recommender
are **trained jointly on all learners** (shared BKT parameters, peer similarity, one difficulty bandit). There are
**no separate per-course models.** What changed is access and scoping:

* Every per-student ML endpoint resolves the student from the session (students) or the path (administrators) and
  only reads that student's rows; one student's answers never enter another student's skill mastery, predictions or
  recommendation list. (Shared population statistics learned at training time are the intended exception.)
* An optional `course_id` (an enrolled course) narrows skills, predictions, adaptive difficulty and recommendations
  to that course: skills of the course, quiz predictions for the course, a difficulty context built from this
  student's attempts in the course, and suggestions from the same topic or unlocked by it.
* `GET /api/students/{id}/courses/{course_id}/guidance` combines those scoped outputs into next steps.
* The online bandit update after a quiz submission still updates the one shared bandit; the context it uses is the
  submitting student's own history.
* Model Evaluation, status and retraining are administrator-only.
* Courses an administrator adds are enrollable immediately but are only recommended after the models are retrained.

## Known limitations

* No e-mail verification, password-reset e-mail, or multi-factor authentication. An administrator resets passwords.
* Login rate-limit counters are per process (see above).
* The single administrator is created only from the command line; there is no UI to create or promote one.
* An administrator may act for a student (submit quizzes, complete lessons) - this is deliberate for support, and
  not separately audited. There is no audit log.
* Sessions have a fixed lifetime (no sliding renewal) and several sessions per user are allowed.
* Alembic migrations are written and tested for SQLite only.
* Existing behaviour that is unchanged: pickle model files in `models/` must only come from a trusted source.
