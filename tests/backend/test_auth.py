"""Authentication: login, sessions, logout, expiry, CSRF/origin, CORS, registration, passwords, first admin."""

import hashlib
import shutil
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api_helpers import assert_error
from backend.app import create_admin
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AuthSession, Student, User, utcnow
from backend.app.security import password_problems
from conftest import ADMIN_EMAIL, ADMIN_PASSWORD, STUDENT_PASSWORD, add_admin, login

GOOD = {"name": "New Person", "email": "new.person@example.edu", "age": 25, "preferred_content": "Videos",
        "password": "A-Long-Passphrase-77"}


def settings_for(app, **over):
    base = dict(database_url=app.state.settings.database_url, seed_on_startup=False, ml_train_on_startup=False,
                cors_origins=("http://localhost:5173",))
    return Settings(**{**base, **over})


@pytest.fixture
def open_app(seeded_template, tmp_path):
    """An app with self-registration enabled."""
    db_path = tmp_path / "open.db"
    shutil.copy(seeded_template, db_path)
    application = create_app(Settings(database_url=f"sqlite:///{db_path.as_posix()}", seed_on_startup=False,
                                      ml_train_on_startup=False, cors_origins=("http://localhost:5173",),
                                      allow_self_registration=True))
    with TestClient(application):
        yield application
    application.state.database.engine.dispose()


# ------------------------------------------------------------------ login
def test_admin_login_returns_identity_and_a_safe_cookie(app):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "admin" and body["user"]["email"] == ADMIN_EMAIL and body["csrf_token"]
    assert "password" not in r.text and "argon2" not in r.text
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "plrs_session=" in cookie
    assert "secure" not in cookie.replace("samesite", "")            # plain-http local development
    assert c.get("/api/auth/me").json()["user"]["id"] == body["user"]["id"]


def test_student_login_and_identity(make_student):
    c, sid, email = make_student()
    me = c.get("/api/auth/me").json()
    assert me["user"]["role"] == "student" and me["user"]["student_id"] == sid and me["student"]["id"] == sid


@pytest.mark.parametrize("email,password", [
    (ADMIN_EMAIL, "Wrong-Password-1"), ("nobody@example.edu", "Whatever-Pass-123"), (ADMIN_EMAIL, " ")])
def test_invalid_login_is_rejected_with_one_generic_message(anon, email, password):
    r = anon.post("/api/auth/login", json={"email": email, "password": password})
    body = assert_error(r, 401, "invalid_credentials")
    assert body["message"] == "Incorrect e-mail or password"            # same text whether or not the user exists
    assert "set-cookie" not in r.headers


def test_login_validates_its_input(anon):
    assert anon.post("/api/auth/login", json={"email": ADMIN_EMAIL}).status_code == 422
    assert anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "x", "role": "admin"}).status_code == 422
    assert anon.post("/api/auth/login", content="not json", headers={"Content-Type": "application/json"}).status_code == 422


def test_passwords_are_argon2_hashed_and_never_stored_plain(app, make_student):
    make_student()
    with app.state.database.SessionLocal() as db:
        for user in db.scalars(select(User)):
            assert user.password_hash.startswith("$argon2id$")
            assert user.password_hash != ADMIN_PASSWORD and STUDENT_PASSWORD not in user.password_hash


def test_a_fresh_database_has_no_default_accounts(seeded_template, tmp_path):
    path = tmp_path / "fresh.db"
    shutil.copy(seeded_template, path)
    application = create_app(Settings(database_url=f"sqlite:///{path.as_posix()}", seed_on_startup=False,
                                      ml_train_on_startup=False))
    with TestClient(application) as c:
        with application.state.database.SessionLocal() as db:
            assert db.scalar(select(User.id)) is None                # no admin, no demo users
        assert c.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin"}).status_code == 401
    application.state.database.engine.dispose()


# ------------------------------------------------------------ lockout & rate limit
def test_account_locks_after_repeated_failures_even_for_the_right_password(app, client):
    email = "lock.me@example.edu"
    assert client.post("/api/admin/users", json={**GOOD, "email": email}).status_code == 201
    anon = TestClient(app)
    for _ in range(5):
        assert anon.post("/api/auth/login", json={"email": email, "password": "Wrong-Password-9"}).status_code == 401
    locked = anon.post("/api/auth/login", json={"email": email, "password": GOOD["password"]})
    assert_error(locked, 429, "rate_limited")
    assert int(locked.headers["retry-after"]) > 0
    with app.state.database.SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.email == email))
    assert client.patch(f"/api/admin/users/{uid}", json={"unlock": True}).json()["locked"] is False
    app.state.limiter.reset(f"login:email:{email}")
    assert anon.post("/api/auth/login", json={"email": email, "password": GOOD["password"]}).status_code == 200


def test_login_attempts_are_rate_limited_per_email(anon):
    codes = [anon.post("/api/auth/login", json={"email": "ghost@example.edu", "password": "Nope-Nope-123"}).status_code
             for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]       # unknown users are throttled identically


def test_deactivated_user_cannot_sign_in_or_keep_a_session(app, client, make_student):
    c, sid, email = make_student()
    uid = c.get("/api/auth/me").json()["user"]["id"]
    assert client.patch(f"/api/admin/users/{uid}", json={"is_active": False}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401                      # existing session dies at once
    assert_error(TestClient(app).post("/api/auth/login", json={"email": email, "password": STUDENT_PASSWORD}),
                 401, "invalid_credentials")


# ---------------------------------------------------------------- sessions
def test_unauthenticated_requests_are_refused(anon):
    assert_error(anon.get("/api/auth/me"), 401, "not_authenticated")
    assert_error(anon.get("/api/students/1"), 401, "not_authenticated")
    assert anon.get("/api/health").json() == {"status": "ok", "database": "ok"}      # no counts for the public


def test_logout_revokes_the_session_server_side(app, client):
    token = client.cookies.get("plrs_session")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    replay = TestClient(app)                                              # replaying the stolen cookie must fail
    replay.cookies.set("plrs_session", token)
    assert replay.get("/api/auth/me").status_code == 401
    with app.state.database.SessionLocal() as db:
        row = db.scalar(select(AuthSession).where(AuthSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        assert row.revoked_at is not None


def test_only_the_token_hash_is_stored(app, client):
    token = client.cookies.get("plrs_session")
    with app.state.database.SessionLocal() as db:
        hashes = list(db.scalars(select(AuthSession.token_hash)))
    assert token not in hashes and hashlib.sha256(token.encode()).hexdigest() in hashes


def test_expired_session_is_rejected(app, client):
    with app.state.database.SessionLocal() as db:
        for s in db.scalars(select(AuthSession)):
            s.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert_error(client.get("/api/auth/me"), 401, "not_authenticated")


def test_session_lifetime_comes_from_settings(app):
    assert app.state.settings.session_ttl_hours == 8
    r = TestClient(app).post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    ttl = (__import__("datetime").datetime.fromisoformat(r.json()["expires_at"]) - utcnow()).total_seconds()
    assert 7.9 * 3600 < ttl <= 8 * 3600
    assert "max-age=28800" in r.headers["set-cookie"].lower()


def test_forged_or_garbage_cookie_is_rejected(app):
    c = TestClient(app)
    for value in ("", "garbage", "A" * 500, hashlib.sha256(b"x").hexdigest()):
        c.cookies.set("plrs_session", value)
        assert c.get("/api/auth/me").status_code == 401


def test_new_login_does_not_revive_a_revoked_session(app, client):
    old = client.cookies.get("plrs_session")
    client.post("/api/auth/logout")
    again = login(app, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert again.cookies.get("plrs_session") != old and again.get("/api/auth/me").status_code == 200


def test_password_reset_signs_the_user_out_everywhere(client, make_student):
    c, sid, email = make_student()
    uid = c.get("/api/auth/me").json()["user"]["id"]
    assert client.patch(f"/api/admin/users/{uid}", json={"password": "Brand-New-Passphrase-1"}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401


def test_production_sets_the_secure_cookie_flag(app):
    prod = settings_for(app, environment="production")
    assert prod.cookie_secure and prod.is_production
    assert not settings_for(app).cookie_secure
    assert settings_for(app, cookie_secure_override=True).cookie_secure
    application = create_app(prod)
    with TestClient(application, base_url="https://testserver") as c:
        r = c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200 and "secure" in r.headers["set-cookie"].lower().replace("samesite", "")
    application.state.database.engine.dispose()


# -------------------------------------------------------- CSRF / origin / CORS
def test_state_changing_requests_need_the_csrf_token(app, client):
    bare = TestClient(app)
    bare.cookies.set("plrs_session", client.cookies.get("plrs_session"))   # valid session, no CSRF header
    payload = {"name": "X Y", "email": "x.y@example.edu", "age": 30, "preferred_content": "Videos"}
    assert_error(bare.post("/api/students", json=payload), 403, "csrf_failed")
    bare.headers["X-CSRF-Token"] = "wrong"
    assert_error(bare.post("/api/students", json=payload), 403, "csrf_failed")
    assert bare.get("/api/students").status_code == 200                    # reads need no token
    bare.headers["X-CSRF-Token"] = client.headers["X-CSRF-Token"]
    assert bare.post("/api/students", json=payload).status_code == 201


def test_csrf_token_is_per_session(app, client, make_student):
    other, _, _ = make_student()
    stolen = {"X-CSRF-Token": other.headers["X-CSRF-Token"]}               # a token from a different session
    r = client.post("/api/students", json={"name": "Q", "email": "q@example.edu", "age": 30,
                                            "preferred_content": "Videos"}, headers=stolen)
    assert_error(r, 403, "csrf_failed")


def test_cross_origin_requests_are_blocked_even_with_a_valid_token(client):
    payload = {"name": "Evil", "email": "evil@example.edu", "age": 30, "preferred_content": "Videos"}
    assert_error(client.post("/api/students", json=payload, headers={"Origin": "https://evil.example"}),
                 403, "origin_not_allowed")
    assert client.post("/api/students", json=payload, headers={"Origin": "http://localhost:5173"}).status_code == 201


def test_login_form_cannot_be_driven_from_another_origin(anon):
    r = anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                  headers={"Origin": "https://evil.example"})
    assert_error(r, 403, "origin_not_allowed")


def test_cors_allows_only_listed_origins_with_credentials(anon):
    ok = anon.options("/api/auth/login", headers={"Origin": "http://localhost:5173",
                                                  "Access-Control-Request-Method": "POST",
                                                  "Access-Control-Request-Headers": "content-type,x-csrf-token"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert ok.headers["access-control-allow-credentials"] == "true"
    bad = anon.options("/api/auth/login", headers={"Origin": "https://evil.example",
                                                   "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers
    assert anon.get("/api/health", headers={"Origin": "https://evil.example"}).headers.get(
        "access-control-allow-origin") is None


def test_wildcard_cors_is_refused(monkeypatch):
    from backend.app.config import get_settings
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValueError):
        get_settings()


def test_responses_carry_security_headers_and_are_not_cacheable(client):
    r = client.get("/api/students/1/summary")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


# ------------------------------------------------------------ registration
def test_registration_is_open_by_default_and_can_be_closed(app, anon, client, seeded_template, tmp_path):
    assert Settings().allow_self_registration is True
    assert anon.get("/api/auth/config").json() == {"allow_self_registration": True}
    db_path = tmp_path / "closed.db"
    shutil.copy(seeded_template, db_path)
    closed = create_app(Settings(database_url=f"sqlite:///{db_path.as_posix()}", seed_on_startup=False,
                                 ml_train_on_startup=False, cors_origins=("http://localhost:5173",),
                                 allow_self_registration=False))
    with TestClient(closed) as c:
        assert c.get("/api/auth/config").json() == {"allow_self_registration": False}
        assert_error(c.post("/api/auth/register", json=GOOD), 403, "registration_disabled")
    closed.state.database.engine.dispose()


def test_registration_creates_an_independent_profile_and_signs_in(open_app):
    c = TestClient(open_app)
    assert c.get("/api/auth/config").json()["allow_self_registration"] is True
    with open_app.state.database.SessionLocal() as db:
        before = db.query(Student).count()
        seeded_ids = set(db.scalars(select(Student.id)))
    r = c.post("/api/auth/register", json=GOOD)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["role"] == "student" and body["student"]["is_synthetic"] is False
    assert body["student"]["id"] not in seeded_ids and "plrs_session" in r.headers["set-cookie"]
    with open_app.state.database.SessionLocal() as db:
        assert db.query(Student).count() == before + 1
    c.headers["X-CSRF-Token"] = body["csrf_token"]
    assert c.get("/api/auth/me").status_code == 200
    assert c.get("/api/students").status_code == 403                       # a new student is not an admin


def test_registration_cannot_attach_to_an_existing_student(open_app):
    c = TestClient(open_app)
    for extra in ({"student_id": 7}, {"role": "admin"}, {"id": 1}, {"is_synthetic": True}):
        assert c.post("/api/auth/register", json={**GOOD, **extra}).status_code == 422
    with open_app.state.database.SessionLocal() as db:
        seeded_email = db.get(Student, 7).email
    assert_error(c.post("/api/auth/register", json={**GOOD, "email": seeded_email}), 409, "email_taken")
    with open_app.state.database.SessionLocal() as db:
        assert db.scalar(select(User.id)) is None


def test_registration_rejects_duplicates_and_weak_passwords(open_app):
    c = TestClient(open_app)
    assert c.post("/api/auth/register", json=GOOD).status_code == 201
    assert_error(TestClient(open_app).post("/api/auth/register", json=GOOD), 409, "email_taken")
    for weak in ("short", "password123", "aaaaaaaaaaaa", "zed.person-1234", "Person-Zed-2026!", "x" * 200):
        r = TestClient(open_app).post("/api/auth/register", json={**GOOD, "name": "Zed Person",
                                                                  "email": "zed.person@example.edu", "password": weak})
        assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "password", weak
    assert TestClient(open_app).post("/api/auth/register", json={**GOOD, "email": "bad", }).status_code == 422


def test_registration_is_rate_limited(open_app):
    c = TestClient(open_app)
    codes = [c.post("/api/auth/register", json={**GOOD, "email": f"p{i}@example.edu"}).status_code for i in range(12)]
    assert codes.count(201) == 10 and codes[-1] == 429


def test_password_policy_unit():
    assert password_problems("A-Long-Passphrase-77") == []
    assert password_problems("short")
    assert password_problems("password123")
    assert password_problems("Maria-Garcia-2026!", email="maria.garcia@example.edu", name="Maria Garcia")


# ----------------------------------------------------------- first admin CLI
def test_first_admin_creation_prompts_and_never_uses_a_default(monkeypatch, tmp_path, capsys):
    url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    secrets = iter(["Correct-Horse-Battery-9"] * 2)
    monkeypatch.setattr(create_admin.getpass, "getpass", lambda prompt="": next(secrets))
    assert create_admin.main(["--email", "Boss@Example.edu"]) == 0
    from backend.app.database import Database
    db = Database(url)
    with db.SessionLocal() as s:
        user = s.scalar(select(User))
        assert user.email == "boss@example.edu" and user.role == "admin" and user.student_id is None
        assert user.password_hash.startswith("$argon2id$")
    db.engine.dispose()
    # a second create is refused; password reset needs the explicit flag
    monkeypatch.setattr(create_admin.getpass, "getpass", lambda prompt="": "Correct-Horse-Battery-9")
    assert create_admin.main(["--email", "boss@example.edu"]) == 1


def test_first_admin_cli_rejects_weak_or_mismatched_passwords(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'cli2.db').as_posix()}")
    monkeypatch.setattr(create_admin.getpass, "getpass", lambda prompt="": "password123")
    assert create_admin.main(["--email", "boss@example.edu"]) == 2
    answers = iter(["Correct-Horse-Battery-9", "Different-Horse-Battery-9"])
    monkeypatch.setattr(create_admin.getpass, "getpass", lambda prompt="": next(answers))
    assert create_admin.main(["--email", "boss@example.edu"]) == 2
    assert create_admin.main(["--email", "not-an-email"]) == 2


def test_admin_password_can_be_reset_from_the_cli(monkeypatch, tmp_path):
    import io
    url = f"sqlite:///{(tmp_path / 'cli3.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr("sys.stdin", io.StringIO("First-Passphrase-1234\n"))
    assert create_admin.main(["--email", "boss@example.edu", "--password-stdin"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO("Second-Passphrase-1234\n"))
    assert create_admin.main(["--email", "boss@example.edu", "--password-stdin", "--reset-password"]) == 0
    application = create_app(Settings(database_url=url, seed_on_startup=False, ml_train_on_startup=False))
    with TestClient(application) as c:
        assert c.post("/api/auth/login", json={"email": "boss@example.edu", "password": "First-Passphrase-1234"}).status_code == 401
        assert c.post("/api/auth/login", json={"email": "boss@example.edu", "password": "Second-Passphrase-1234"}).status_code == 200
    application.state.database.engine.dispose()
