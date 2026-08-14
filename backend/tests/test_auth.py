import re

VALID_PASSWORD = "Str0ng!Passw0rd"


def _extract_token(email_body: str) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", email_body)
    assert match, f"No token found in email body: {email_body}"
    return match.group(1)


def _signup(client, email_outbox, email="ada@example.com", password=VALID_PASSWORD):
    resp = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Ada Lovelace",
            "email": email,
            "password": password,
            "confirm_password": password,
            "accept_terms": True,
        },
    )
    return resp


def _verify(client, email_outbox):
    token = _extract_token(email_outbox[-1].text_body)
    return client.post("/api/auth/verify-email", json={"token": token})


def _signup_and_verify(client, email_outbox, email="ada@example.com", password=VALID_PASSWORD):
    _signup(client, email_outbox, email, password)
    _verify(client, email_outbox)


class TestSignup:
    def test_signup_success(self, client, email_outbox):
        resp = _signup(client, email_outbox)
        assert resp.status_code == 201
        assert len(email_outbox) == 1
        assert email_outbox[0].to == "ada@example.com"

    def test_duplicate_email_rejected(self, client, email_outbox):
        _signup(client, email_outbox)
        resp = _signup(client, email_outbox)
        assert resp.status_code == 409

    def test_invalid_email_rejected(self, client, email_outbox):
        resp = client.post(
            "/api/auth/signup",
            json={
                "full_name": "Ada",
                "email": "not-an-email",
                "password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
                "accept_terms": True,
            },
        )
        assert resp.status_code == 422

    def test_weak_password_rejected(self, client, email_outbox):
        resp = client.post(
            "/api/auth/signup",
            json={
                "full_name": "Ada",
                "email": "ada@example.com",
                "password": "weak",
                "confirm_password": "weak",
                "accept_terms": True,
            },
        )
        assert resp.status_code == 422

    def test_password_mismatch_rejected(self, client, email_outbox):
        resp = client.post(
            "/api/auth/signup",
            json={
                "full_name": "Ada",
                "email": "ada@example.com",
                "password": VALID_PASSWORD,
                "confirm_password": "Different1!",
                "accept_terms": True,
            },
        )
        assert resp.status_code == 422

    def test_terms_not_accepted_rejected(self, client, email_outbox):
        resp = client.post(
            "/api/auth/signup",
            json={
                "full_name": "Ada",
                "email": "ada@example.com",
                "password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
                "accept_terms": False,
            },
        )
        assert resp.status_code == 422


class TestEmailVerification:
    def test_verify_email_activates_account(self, client, email_outbox):
        _signup(client, email_outbox)
        resp = _verify(client, email_outbox)
        assert resp.status_code == 200

        # login now succeeds
        login_resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
        )
        assert login_resp.status_code == 200
        assert login_resp.json()["email_verified"] is True

    def test_verify_token_single_use(self, client, email_outbox):
        _signup(client, email_outbox)
        token = _extract_token(email_outbox[-1].text_body)
        first = client.post("/api/auth/verify-email", json={"token": token})
        second = client.post("/api/auth/verify-email", json={"token": token})
        assert first.status_code == 200
        assert second.status_code == 400

    def test_invalid_token_rejected(self, client, email_outbox):
        resp = client.post("/api/auth/verify-email", json={"token": "bogus-token"})
        assert resp.status_code == 400

    def test_resend_verification(self, client, email_outbox):
        _signup(client, email_outbox)
        resp = client.post("/api/auth/resend-verification", json={"email": "ada@example.com"})
        assert resp.status_code == 200
        assert len(email_outbox) == 2

    def test_resend_verification_unknown_email_is_silent(self, client, email_outbox):
        resp = client.post("/api/auth/resend-verification", json={"email": "nobody@example.com"})
        assert resp.status_code == 200
        assert len(email_outbox) == 0


class TestLogin:
    def test_login_before_verification_blocked(self, client, email_outbox):
        _signup(client, email_outbox)
        resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
        )
        assert resp.status_code == 403

    def test_wrong_password_rejected(self, client, email_outbox):
        _signup_and_verify(client, email_outbox)
        resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": "WrongPass1!"}
        )
        assert resp.status_code == 401

    def test_unknown_email_rejected(self, client, email_outbox):
        resp = client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": VALID_PASSWORD}
        )
        assert resp.status_code == 401

    def test_login_sets_session_and_csrf_cookies(self, client, email_outbox):
        _signup_and_verify(client, email_outbox)
        resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
        )
        assert "aiagent_session" in resp.cookies
        assert "aiagent_csrf" in resp.cookies

    def test_account_lockout_after_repeated_failures(self, client, email_outbox):
        _signup_and_verify(client, email_outbox)
        for _ in range(5):
            client.post(
                "/api/auth/login", json={"email": "ada@example.com", "password": "WrongPass1!"}
            )
        locked_resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
        )
        assert locked_resp.status_code == 423


class TestLogout:
    def _login(self, client, email_outbox):
        _signup_and_verify(client, email_outbox)
        resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
        )
        csrf = resp.cookies["aiagent_csrf"]
        return csrf

    def test_logout_requires_csrf_header(self, client, email_outbox):
        self._login(client, email_outbox)
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 403

    def test_logout_revokes_session(self, client, email_outbox):
        csrf = self._login(client, email_outbox)
        resp = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200

        me_resp = client.get("/api/users/me")
        assert me_resp.status_code == 401

    def test_protected_endpoint_requires_session(self, client, email_outbox):
        resp = client.get("/api/users/me")
        assert resp.status_code == 401


class TestForgotAndResetPassword:
    def test_forgot_password_generic_response_for_unknown_email(self, client, email_outbox):
        resp = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
        assert resp.status_code == 200
        assert len(email_outbox) == 0

    def test_forgot_password_sends_email_for_known_user(self, client, email_outbox):
        _signup_and_verify(client, email_outbox)
        resp = client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
        assert resp.status_code == 200
        assert len(email_outbox) == 2  # verification + reset

    def test_reset_password_with_valid_token(self, client, email_outbox):
        _signup_and_verify(client, email_outbox)
        client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
        token = _extract_token(email_outbox[-1].text_body)

        new_password = "NewStr0ng!Pass"
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": new_password, "confirm_password": new_password},
        )
        assert resp.status_code == 200

        login_resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": new_password}
        )
        assert login_resp.status_code == 200

        old_login_resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
        )
        assert old_login_resp.status_code == 401

    def test_reset_password_token_single_use(self, client, email_outbox):
        _signup_and_verify(client, email_outbox)
        client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
        token = _extract_token(email_outbox[-1].text_body)

        new_password = "NewStr0ng!Pass"
        first = client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": new_password, "confirm_password": new_password},
        )
        second = client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": "Another1!Pass", "confirm_password": "Another1!Pass"},
        )
        assert first.status_code == 200
        assert second.status_code == 400

    def test_reset_password_revokes_existing_sessions(self, client, email_outbox):
        _signup_and_verify(client, email_outbox)
        login_resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
        )
        assert login_resp.status_code == 200

        client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
        token = _extract_token(email_outbox[-1].text_body)
        new_password = "NewStr0ng!Pass"
        client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": new_password, "confirm_password": new_password},
        )

        me_resp = client.get("/api/users/me")
        assert me_resp.status_code == 401


class TestProfileAndSettings:
    def _login(self, client, email_outbox):
        _signup_and_verify(client, email_outbox)
        resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
        )
        return resp.cookies["aiagent_csrf"]

    def test_get_me(self, client, email_outbox):
        self._login(client, email_outbox)
        resp = client.get("/api/users/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == "ada@example.com"

    def test_update_settings_theme(self, client, email_outbox):
        csrf = self._login(client, email_outbox)
        resp = client.patch(
            "/api/users/me/settings",
            json={"theme": "light"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["theme"] == "light"

        get_resp = client.get("/api/users/me/settings")
        assert get_resp.json()["theme"] == "light"

    def test_change_password_requires_current_password(self, client, email_outbox):
        csrf = self._login(client, email_outbox)
        resp = client.post(
            "/api/users/me/change-password",
            json={
                "current_password": "WrongCurrent1!",
                "new_password": "NewStr0ng!Pass",
                "confirm_password": "NewStr0ng!Pass",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 400

    def test_change_password_success(self, client, email_outbox):
        csrf = self._login(client, email_outbox)
        new_password = "NewStr0ng!Pass"
        resp = client.post(
            "/api/users/me/change-password",
            json={
                "current_password": VALID_PASSWORD,
                "new_password": new_password,
                "confirm_password": new_password,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200

        login_resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": new_password}
        )
        assert login_resp.status_code == 200


class TestSessions:
    def test_list_sessions_marks_current(self, client, email_outbox):
        _signup_and_verify(client, email_outbox)
        client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
        )
        resp = client.get("/api/auth/sessions")
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 1
        assert sessions[0]["is_current"] is True

    def test_logout_all_revokes_session(self, client, email_outbox):
        _signup_and_verify(client, email_outbox)
        login_resp = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
        )
        csrf = login_resp.cookies["aiagent_csrf"]
        resp = client.post("/api/auth/logout-all", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200
        me_resp = client.get("/api/users/me")
        assert me_resp.status_code == 401
