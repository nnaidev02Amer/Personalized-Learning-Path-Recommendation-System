# REST API (Phase 3)

Base URL: `http://127.0.0.1:8000`. Interactive docs (Swagger UI): `/docs`; OpenAPI JSON: `/openapi.json`.

**Every route except `/api/health` (limited), `/api/auth/config`, `/api/auth/login` and `/api/auth/register`
requires a signed-in session** (HttpOnly cookie). State-changing requests (POST/PUT/PATCH/DELETE) must also send
the session's CSRF token in the `X-CSRF-Token` header (returned by login / `GET /api/auth/me`). See
`docs/AUTHENTICATION.md` for the full model. In the tables below, **Admin** means administrator only;
**Owner/Admin** means the student the record belongs to, or an administrator; **Any** means any signed-in user.

All errors use one shape:

```json
{"error": {"code": "prerequisites_not_met", "message": "Complete the prerequisites for PY102 first",
           "details": [{"id": 1, "code": "PY101", "title": "Python Fundamentals"}]}}
```

| Status | `code` values |
|---|---|
| 401 | `not_authenticated` (no/expired/revoked session), `invalid_credentials` |
| 403 | `forbidden`, `admin_required`, `csrf_failed`, `origin_not_allowed`, `registration_disabled`, `cannot_deactivate_self`, `last_admin` |
| 404 | `not_found` (also returned when a student asks for another student's record, so ids cannot be probed) |
| 429 | `rate_limited` (too many sign-in attempts or account temporarily locked; `Retry-After` header) |
| 409 | `course_code_taken`, `course_in_use`, `course_archived`, `account_exists`, `email_taken`, `already_enrolled`, `prerequisites_not_met`, `not_enrolled`, `not_completed`, `enrollment_not_active`, `invalid_status_change`, `conflict` |
| 422 | `validation_error` (with `details: [{field, message}]`) |
| 503 | `ml_insufficient_data` (AI endpoints when the database has too little data to train: < 10 students with 2+ enrolments or < 30 quiz attempts) |
| 500 | `internal_error` (no stack trace leaked) |

## Authentication
| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/api/auth/config` | Public | `{allow_self_registration}` |
| POST | `/api/auth/login` | Public | `{email, password}` → sets the session cookie, returns `{user, student, csrf_token, expires_at}`. Rate limited; 5 failures lock the account for 15 minutes |
| POST | `/api/auth/logout` | Session | Revokes the session and clears the cookie → 204 |
| GET | `/api/auth/me` | Any | Current user, their student profile and a fresh CSRF token |
| POST | `/api/auth/register` | Public* | Self-registration (`name, email, age, preferred_content, learning_style?, daily_goal_minutes?, password`). Always creates a NEW student profile. *403 `registration_disabled` unless `ALLOW_SELF_REGISTRATION=true` |

## Administration (Admin)
| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/overview` | Totals: registered students, request counts (pending/approved/rejected), courses, enrolments, attempts, average score, top courses, at-risk count |
| GET | `/api/admin/course-enrollments` | Every course with enrolled / in-progress / completed counts and pending requests |
| GET | `/api/admin/enrollment-requests?status=&search=&limit=&offset=` | All enrolment requests with student and course |
| POST | `/api/admin/enrollment-requests/{request_id}/approve` | Approve: creates the enrolment (prerequisites re-checked). 409 `request_not_pending` if already decided |
| POST | `/api/admin/enrollment-requests/{request_id}/reject` | Reject, optional `{note}` shown to the student |
| GET | `/api/admin/students?search=&at_risk=&limit=&offset=` | Monitoring table: every learner with enrolment and performance totals |
| GET | `/api/admin/users?role=&search=&limit=&offset=` | Login accounts (never includes password hashes) |
| POST | `/api/admin/users` | Create a NEW learner profile with a login → 201 |
| POST | `/api/admin/students/{id}/account` | Give an EXISTING learner (e.g. a seeded one) a login, `{password}`; the login e-mail is the profile's e-mail → 201 |
| PATCH | `/api/admin/users/{id}` | `is_active`, `password` (reset; revokes sessions), `unlock` |
| POST | `/api/admin/users/{id}/revoke-sessions` | Sign the user out everywhere → 204 |

## Meta
| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/api/health` | Public | Liveness + database check. Row counts only for signed-in users |
| GET | `/api/meta` | Any | Allowed learning styles, content types, difficulties, topics, statuses |

## Students
| Method | Path | Description |
|---|---|---|
| GET | `/api/students?search=&learning_style=&limit=20&offset=0` | Paginated list (`{items,total,limit,offset}`) |
| POST | `/api/students` | **Admin.** Create (`name, email, age, learning_style?, preferred_content, daily_goal_minutes?`) → 201 |
| GET | `/api/students/{id}` | Profile |
| PATCH | `/api/students/{id}` | Partial update |
| DELETE | `/api/students/{id}` | **Admin only.** Delete with all history (enrolments, attempts, activity, the login) → 204 |
| GET | `/api/students/{id}/summary` | Dashboard numbers: courses by status, lessons done/pending, quiz average, minutes (7 days / total), streak |
| GET | `/api/students/{id}/progress?weeks=12` | Overall completion, per-course progress, weekly activity, quiz score timeline, score trend (half-vs-half and slope/week), scores by topic |
| GET | `/api/students/{id}/quiz-attempts?limit=50` | Attempt history, newest first |
| GET | `/api/students/{id}/activity?limit=100` | Activity log, newest first |
| POST | `/api/students/{id}/activity` | Log self-study time (`minutes`, `activity_date?`, `course_id?`) → 201 |

Every `/api/students/{id}/…` route below is **Owner/Admin**; `GET /api/students` is **Admin**.

## Courses & quizzes
| Method | Path | Description |
|---|---|---|
| GET | `/api/courses?search=&topic=&difficulty=&content_format=&limit=50&offset=0` | Catalogue with enrolment count and average rating |
| GET | `/api/courses/{id}` | Detail: description, lessons, prerequisites, quizzes (archived courses: only for students already enrolled) |
| POST | `/api/courses` | **Admin.** Create a course with lessons and an optional quiz → 201 |
| PATCH | `/api/courses/{id}` | **Admin.** Edit metadata; `is_active=false` archives (hidden from the catalogue, enrolments kept) |
| DELETE | `/api/courses/{id}` | **Admin.** Only for a course with no enrolments or attempts (else 409 `course_in_use`; archive it) → 204 |
| GET | `/api/quizzes/{id}` | Questions and options (**answers are not exposed**); students only for courses they are enrolled in |

## Learning workflow
| Method | Path | Description |
|---|---|---|
| GET | `/api/students/{id}/enrollments?status=` | Enrolments with progress and next lesson |
| POST | `/api/students/{id}/enrollments` | Enrol (`course_id`). Students may do this only for **unlocked** courses (locked → 403 `approval_required`); the administrator can enrol anyone. Enforces prerequisites → 201 |
| GET | `/api/students/{id}/enrollment-requests?status=` | The student's own requests (`pending`, `approved`, `rejected`, `cancelled`) with the admin's note |
| POST | `/api/students/{id}/enrollment-requests` | Ask for access to a **locked** course (`course_id`). 409 `course_unlocked` (enrol directly), `request_pending`, `already_enrolled`, `prerequisites_not_met`, `course_archived` → 201 |
| DELETE | `/api/students/{id}/enrollment-requests/{request_id}` | Withdraw a request that is still pending → 204 |
| GET | `/api/enrollments/{id}` | One enrolment |
| PATCH | `/api/enrollments/{id}` | `status: active|dropped`, `rating: 1-5` (completed courses only) |
| POST | `/api/enrollments/{id}/lessons/{lesson_id}/complete` | Mark lesson done (idempotent), logs activity, auto-completes the course after the last lesson |
| POST | `/api/students/{id}/quizzes/{quiz_id}/attempts` | Submit `answers: [option index…]`, `time_taken_min?`. Server grades and returns score + per-question feedback → 201 |

## AI / ML (Phase 5)
| Method | Path | Description |
|---|---|---|
| GET | `/api/ml/status` | **Admin.** Trained?, training time, training-data provenance, assistant provider |
| GET | `/api/ml/evaluation` | **Admin.** Full evaluation report (all models vs baselines, bootstrap CIs) |
| POST | `/api/ml/retrain` | **Admin.** Retrain every model on the current database |
| GET | `/api/students/{id}/recommendations?method=hybrid|content|collaborative|popularity&limit=5&course_id=` | Ranked unlocked courses with reasons and component scores. With `course_id` (an enrolled course): only courses in the same topic or unlocked by it. Archived courses are never recommended. Changed lists are logged |
| GET | `/api/students/{id}/recommendation-history?limit=20` | What was recommended to this student, newest first |
| GET | `/api/students/{id}/skills?course_id=` | BKT mastery per skill, gaps, untested skills, topic means (with `course_id`: that course's skills) |
| GET | `/api/students/{id}/adaptive-difficulty?course_id=` | LinUCB suggestion + expected success per level (with `course_id`: context built from this student's attempts in that course) |
| GET | `/api/students/{id}/predictions?course_id=` | Predicted quiz score (± model MAE) per enrolled course (or one course) |
| GET | `/api/students/{id}/courses/{course_id}/guidance` | Next steps for one enrolled course: weak skills, difficulty, predicted quiz score, related next courses |
| GET | `/api/students/{id}/learning-style` | Predicted style, probabilities, `reliable` flag and advice |
| POST | `/api/students/{id}/assistant` | `{message}` → grounded answer (`source`: `rules` or `claude`) |

Course scoping filters or conditions one learner's own data; the models themselves are still trained jointly on all
learners (there are no per-course models). Every model response includes `model_output: true`, `trained_at`, `student_history`
(`synthetic (seeded)` / `real`) and the model's evaluation. See `docs/ML_MODELS.md`.

## Database tables

```
students ─┬─< enrollments >── courses ─┬─< lessons
          │        └─< lesson_completions│
          ├─< quiz_attempts >── quizzes ─┘─< quiz_questions
          └─< activity_logs              courses >─< course_prerequisites >─ courses
```

| Table | Key columns |
|---|---|
| `students` | id, name, email (unique), age, learning_style, preferred_content, daily_goal_minutes, is_synthetic, created_at |
| `courses` | id, code (unique), title, description, topic, difficulty, level 1–3, content_format, duration_hours, skills (JSON) |
| `course_prerequisites` | course_id, prerequisite_id |
| `lessons` | id, course_id, position, title, duration_min |
| `quizzes` | id, course_id, title, difficulty, pass_score |
| `quiz_questions` | id, quiz_id, position, prompt, options (JSON), correct_option, skill, explanation |
| `enrollments` | id, student_id, course_id (unique pair), status, rating 1–5, enrolled_at, completed_at |
| `lesson_completions` | id, enrollment_id, lesson_id (unique pair), completed_at |
| `quiz_attempts` | id, student_id, quiz_id, score 0–100, correct, total, answers (JSON), time_taken_min, attempted_at |
| `activity_logs` | id, student_id, course_id, activity_date, minutes, kind (lesson/quiz/study) |

## Sample data — what is real and what is synthetic
* **Hand-written content:** 24 courses in 6 topics, 120 lessons, 96 quiz questions with answer keys.
* **From `sample_data.csv`:** the 100 student profiles (id, age, learning style, preferred
  content, daily study minutes). Names/e-mails are generated placeholders (`@example.edu`).
* **Synthetic (seeded, `is_synthetic = true`):** enrolments, lesson completions, quiz attempts,
  ratings, per-question quiz answers (incl. ~35 % retakes) and activity for the last 12 weeks,
  constrained to match each original row. Measured on the seeded DB: completed courses =
  `CompletedCourses` for 100 % of students; mean quiz score within 1.3 points of `AverageScore`
  on average (bound 50/N for N answered questions); active-course lesson progress correlates
  0.94 with `Progress`; daily minutes correlate 0.35 with `SessionTime`.
* The history is anchored to the date of seeding. Re-run `python -m backend.app.seed --reset`
  to refresh it later.
