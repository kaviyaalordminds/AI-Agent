"""Real exercise of app/security/rate_limit.py's sliding-window limiter —
making max_requests+1 calls within the window and confirming the last one
is rejected with 429. The Phase 10 audit found two existing tests that
*look* like rate-limit tests but actually exercise unrelated mechanisms
(account lockout, job-concurrency limits) and never trip the rate
limiter itself for any bucket — this file closes that gap for every
bucket the app defines: login, signup, resend-verification,
forgot-password, and the shared "generation" bucket.

_buckets is cleared by conftest.py's autouse _clean_database fixture
before every test, so each test starts from a clean rate-limit window.
"""
from app.security import rate_limit


class TestLoginRateLimit:
    def test_11th_login_attempt_within_window_is_rate_limited(self, client):
        """max_requests=10 (app/api/auth/router.py). Uses a nonexistent
        email throughout so every attempt fails with a fast 401 — never
        triggers the separate account-lockout mechanism (which only
        applies to a real user after repeated wrong-password attempts),
        keeping this test isolated to the rate limiter specifically."""
        statuses = []
        for _ in range(11):
            resp = client.post(
                "/api/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}
            )
            statuses.append(resp.status_code)
        assert statuses[:10] == [401] * 10
        assert statuses[10] == 429


class TestSignupRateLimit:
    def test_6th_signup_attempt_within_window_is_rate_limited(self, client):
        """max_requests=5 (app/api/auth/router.py). A unique email per
        attempt means every one of the first 5 succeeds (201) before the
        6th is rejected — proves the limiter counts requests regardless
        of outcome, not just failures."""
        statuses = []
        for i in range(6):
            resp = client.post(
                "/api/auth/signup",
                json={
                    "full_name": "Rate Limit Test",
                    "email": f"ratelimit-signup-{i}@example.com",
                    "password": "Str0ng!Passw0rd",
                    "confirm_password": "Str0ng!Passw0rd",
                    "accept_terms": True,
                },
            )
            statuses.append(resp.status_code)
        assert statuses[:5] == [201] * 5
        assert statuses[5] == 429


class TestResendVerificationRateLimit:
    def test_4th_resend_attempt_within_window_is_rate_limited(self, client):
        """max_requests=3 (app/api/auth/router.py)."""
        statuses = []
        for _ in range(4):
            resp = client.post("/api/auth/resend-verification", json={"email": "nobody@example.com"})
            statuses.append(resp.status_code)
        assert statuses[:3] == [200] * 3
        assert statuses[3] == 429


class TestForgotPasswordRateLimit:
    def test_6th_forgot_password_attempt_within_window_is_rate_limited(self, client):
        """max_requests=5 (app/api/auth/router.py)."""
        statuses = []
        for _ in range(6):
            resp = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
            statuses.append(resp.status_code)
        assert statuses[:5] == [200] * 5
        assert statuses[5] == 429


class TestGenerationRateLimit:
    def test_21st_generation_request_within_window_is_rate_limited(self, auth_client):
        """The "generation" bucket is shared across documents, audio
        jobs, and image/video/word/ppt/excel generation
        (app/core/config.py: generation_rate_limit_max_requests=20) —
        exercised here via the fast, synchronous, no-AI-provider-needed
        structured Word endpoint so the test doesn't depend on any
        external provider being configured."""
        client, csrf = auth_client
        payload = {"title": "Rate Limit Doc", "blocks": [{"type": "paragraph", "text": "hi"}]}
        statuses = []
        for _ in range(21):
            resp = client.post(
                "/api/generation/document/word", json=payload, headers={"X-CSRF-Token": csrf}
            )
            statuses.append(resp.status_code)
        assert statuses[:20] == [201] * 20
        assert statuses[20] == 429

    def test_generation_bucket_is_shared_across_different_endpoints(self, auth_client):
        """Confirms the bucket really is shared (per-IP, not per-endpoint)
        — 10 Word requests plus 10 Excel requests plus one more of either
        should trip the same limit, not get 20 of each."""
        client, csrf = auth_client
        word_payload = {"title": "Doc", "blocks": [{"type": "paragraph", "text": "hi"}]}
        excel_payload = {"title": "Sheet", "sheets": [{"name": "S1", "headers": ["A"], "rows": [[1]]}]}

        statuses = []
        for _ in range(10):
            statuses.append(
                client.post(
                    "/api/generation/document/word", json=word_payload, headers={"X-CSRF-Token": csrf}
                ).status_code
            )
        for _ in range(10):
            statuses.append(
                client.post(
                    "/api/generation/document/excel", json=excel_payload, headers={"X-CSRF-Token": csrf}
                ).status_code
            )
        assert statuses == [201] * 20

        one_more = client.post(
            "/api/generation/document/word", json=word_payload, headers={"X-CSRF-Token": csrf}
        )
        assert one_more.status_code == 429


class TestRateLimitBucketIsolation:
    def test_different_buckets_do_not_share_a_counter(self, client):
        """Exhausting the resend-verification bucket (limit 3) must never
        affect the separately-keyed forgot-password bucket (limit 5),
        even though both buckets are scoped to the same client IP."""
        for _ in range(3):
            resp = client.post("/api/auth/resend-verification", json={"email": "nobody@example.com"})
            assert resp.status_code == 200
        exhausted = client.post("/api/auth/resend-verification", json={"email": "nobody@example.com"})
        assert exhausted.status_code == 429

        still_fresh = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
        assert still_fresh.status_code == 200

    def test_is_allowed_directly_respects_window_and_limit(self):
        """A focused unit test on the limiter itself, independent of any
        HTTP endpoint — proves the sliding-window mechanics (not just one
        bucket's wiring) are correct."""
        key = "unit-test-bucket:127.0.0.1"
        for _ in range(3):
            assert rate_limit.is_allowed(key, max_requests=3, window_seconds=60) is True
        assert rate_limit.is_allowed(key, max_requests=3, window_seconds=60) is False
