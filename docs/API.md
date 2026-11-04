# REST API (Phase 3)

Base URL: `http://127.0.0.1:8000`. Interactive docs (Swagger UI): `/docs`; OpenAPI JSON: `/openapi.json`.

All errors use one shape:

```json
{"error": {"code": "prerequisites_not_met", "message": "Complete the prerequisites for PY102 first",
           "details": [{"id": 1, "code": "PY101", "title": "Python Fundamentals"}]}}
```

| Status | `code` values |
|---|---|
| 404 | `not_found` |
| 409 | `email_taken`, `already_enrolled`, `prerequisites_not_met`, `not_enrolled`, `not_completed`, `enrollment_not_active`, `invalid_status_change`, `conflict` |
| 422 | `validation_error` (with `details: [{field, message}]`) |
| 500 | `internal_error` (no stack trace leaked) |

## Meta
| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness + database check + row counts |
| GET | `/api/meta` | Allowed learning styles, content types, difficulties, topics, statuses |

## Students
| Method | Path | Description |
|---|---|---|
| GET | `/api/students?search=&learning_style=&limit=20&offset=0` | Paginated list (`{items,total,limit,offset}`) |
| POST | `/api/students` | Create (`name, email, age, learning_style?, preferred_content, daily_goal_minutes?`) → 201 |
| GET | `/api/students/{id}` | Profile |
| PATCH | `/api/students/{id}` | Partial update |
| DELETE | `/api/students/{id}` | Delete with all history → 204 |
| GET | `/api/students/{id}/summary` | Dashboard numbers: courses by status, lessons done/pending, quiz average, minutes (7 days / total), streak |
| GET | `/api/students/{id}/progress?weeks=12` | Overall completion, per-course progress, weekly activity, quiz score timeline, score trend (half-vs-half and slope/week), scores by topic |
| GET | `/api/students/{id}/quiz-attempts?limit=50` | Attempt history, newest first |
| GET | `/api/students/{id}/activity?limit=100` | Activity log, newest first |
| POST | `/api/students/{id}/activity` | Log self-study time (`minutes`, `activity_date?`, `course_id?`) → 201 |

## Courses & quizzes
| Method | Path | Description |
|---|---|---|
| GET | `/api/courses?search=&topic=&difficulty=&content_format=&limit=50&offset=0` | Catalogue with enrolment count and average rating |
| GET | `/api/courses/{id}` | Detail: description, lessons, prerequisites, quizzes |
| GET | `/api/quizzes/{id}` | Questions and options (**answers are not exposed**) |

## Learning workflow
| Method | Path | Description |
|---|---|---|
| GET | `/api/students/{id}/enrollments?status=` | Enrolments with progress and next lesson |
| POST | `/api/students/{id}/enrollments` | Enrol (`course_id`). Enforces prerequisites; re-activates a dropped enrolment → 201 |
| GET | `/api/enrollments/{id}` | One enrolment |
| PATCH | `/api/enrollments/{id}` | `status: active|dropped`, `rating: 1-5` (completed courses only) |
| POST | `/api/enrollments/{id}/lessons/{lesson_id}/complete` | Mark lesson done (idempotent), logs activity, auto-completes the course after the last lesson |
| POST | `/api/students/{id}/quizzes/{quiz_id}/attempts` | Submit `answers: [option index…]`, `time_taken_min?`. Server grades and returns score + per-question feedback → 201 |

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
  ratings and activity for the last 12 weeks, constrained to match each original row. Measured
  on the seeded DB: completed courses = `CompletedCourses` for 100 % of students; mean quiz
  score within 0.18 points of `AverageScore` on average; active-course lesson progress
  correlates 0.94 with `Progress`; daily minutes correlate 0.36 with `SessionTime`.
* The history is anchored to the date of seeding. Re-run `python -m backend.app.seed --reset`
  to refresh it later.
