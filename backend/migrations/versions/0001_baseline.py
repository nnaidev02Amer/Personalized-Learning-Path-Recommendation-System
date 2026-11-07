"""Baseline: the schema as it existed before authentication (10 tables).

Frozen SQLite DDL, deliberately independent of the current ORM models. A database that already
has these tables is *stamped* at this revision (python -m backend.app.migrate) -- never
re-created -- so no existing row is touched.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

BASELINE_TABLES = ("courses", "students", "activity_logs", "course_prerequisites", "enrollments",
                   "lessons", "quizzes", "lesson_completions", "quiz_attempts", "quiz_questions")

DDL = [
    """CREATE TABLE courses (
	id INTEGER NOT NULL, 
	code VARCHAR(20) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	topic VARCHAR(60) NOT NULL, 
	difficulty VARCHAR(20) NOT NULL, 
	level INTEGER NOT NULL, 
	content_format VARCHAR(30) NOT NULL, 
	duration_hours FLOAT NOT NULL, 
	skills JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
)""",
    """CREATE INDEX ix_courses_topic ON courses (topic)""",
    """CREATE TABLE students (
	id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	age INTEGER NOT NULL, 
	learning_style VARCHAR(30), 
	preferred_content VARCHAR(30) NOT NULL, 
	daily_goal_minutes FLOAT NOT NULL, 
	is_synthetic BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
)""",
    """CREATE UNIQUE INDEX ix_students_email ON students (email)""",
    """CREATE TABLE activity_logs (
	id INTEGER NOT NULL, 
	student_id INTEGER NOT NULL, 
	course_id INTEGER, 
	activity_date DATE NOT NULL, 
	minutes FLOAT NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE SET NULL
)""",
    """CREATE INDEX ix_activity_logs_activity_date ON activity_logs (activity_date)""",
    """CREATE INDEX ix_activity_logs_student_id ON activity_logs (student_id)""",
    """CREATE TABLE course_prerequisites (
	course_id INTEGER NOT NULL, 
	prerequisite_id INTEGER NOT NULL, 
	PRIMARY KEY (course_id, prerequisite_id), 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE, 
	FOREIGN KEY(prerequisite_id) REFERENCES courses (id) ON DELETE CASCADE
)""",
    """CREATE TABLE enrollments (
	id INTEGER NOT NULL, 
	student_id INTEGER NOT NULL, 
	course_id INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	rating INTEGER, 
	enrolled_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (student_id, course_id), 
	CONSTRAINT rating_range CHECK (rating IS NULL OR (rating BETWEEN 1 AND 5)), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_enrollments_course_id ON enrollments (course_id)""",
    """CREATE INDEX ix_enrollments_student_id ON enrollments (student_id)""",
    """CREATE TABLE lessons (
	id INTEGER NOT NULL, 
	course_id INTEGER NOT NULL, 
	position INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	duration_min INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (course_id, position), 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_lessons_course_id ON lessons (course_id)""",
    """CREATE TABLE quizzes (
	id INTEGER NOT NULL, 
	course_id INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	difficulty VARCHAR(20) NOT NULL, 
	pass_score FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_quizzes_course_id ON quizzes (course_id)""",
    """CREATE TABLE lesson_completions (
	id INTEGER NOT NULL, 
	enrollment_id INTEGER NOT NULL, 
	lesson_id INTEGER NOT NULL, 
	completed_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (enrollment_id, lesson_id), 
	FOREIGN KEY(enrollment_id) REFERENCES enrollments (id) ON DELETE CASCADE, 
	FOREIGN KEY(lesson_id) REFERENCES lessons (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_lesson_completions_enrollment_id ON lesson_completions (enrollment_id)""",
    """CREATE TABLE quiz_attempts (
	id INTEGER NOT NULL, 
	student_id INTEGER NOT NULL, 
	quiz_id INTEGER NOT NULL, 
	score FLOAT NOT NULL, 
	correct INTEGER, 
	total INTEGER, 
	answers JSON, 
	time_taken_min FLOAT, 
	attempted_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(quiz_id) REFERENCES quizzes (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_quiz_attempts_attempted_at ON quiz_attempts (attempted_at)""",
    """CREATE INDEX ix_quiz_attempts_quiz_id ON quiz_attempts (quiz_id)""",
    """CREATE INDEX ix_quiz_attempts_student_id ON quiz_attempts (student_id)""",
    """CREATE TABLE quiz_questions (
	id INTEGER NOT NULL, 
	quiz_id INTEGER NOT NULL, 
	position INTEGER NOT NULL, 
	prompt TEXT NOT NULL, 
	options JSON NOT NULL, 
	correct_option INTEGER NOT NULL, 
	skill VARCHAR(60) NOT NULL, 
	explanation TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(quiz_id) REFERENCES quizzes (id) ON DELETE CASCADE
)""",
    """CREATE INDEX ix_quiz_questions_quiz_id ON quiz_questions (quiz_id)""",
]


def upgrade() -> None:
    for statement in DDL:
        op.execute(statement)


def downgrade() -> None:
    raise RuntimeError("The baseline is never downgraded (it would delete every student record).")
