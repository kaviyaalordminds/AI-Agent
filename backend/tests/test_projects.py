def test_create_project(auth_client):
    client, csrf = auth_client
    resp = client.post(
        "/api/projects",
        json={"name": "Manufacturing HRMS", "description": "HR system for a factory"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Manufacturing HRMS"
    assert body["status"] == "active"


def test_create_project_requires_csrf(auth_client):
    client, _csrf = auth_client
    resp = client.post("/api/projects", json={"name": "No CSRF"})
    assert resp.status_code == 403


def test_create_project_empty_name_rejected(auth_client):
    client, csrf = auth_client
    resp = client.post("/api/projects", json={"name": "   "}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 422


def test_list_projects_defaults_to_active(auth_client):
    client, csrf = auth_client
    client.post("/api/projects", json={"name": "Active One"}, headers={"X-CSRF-Token": csrf})
    archived = client.post(
        "/api/projects", json={"name": "Will Archive"}, headers={"X-CSRF-Token": csrf}
    ).json()
    client.post(f"/api/projects/{archived['id']}/archive", headers={"X-CSRF-Token": csrf})

    resp = client.get("/api/projects")
    names = [p["name"] for p in resp.json()]
    assert "Active One" in names
    assert "Will Archive" not in names


def test_list_projects_empty_for_new_user(auth_client):
    client, _csrf = auth_client
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_project(auth_client):
    client, csrf = auth_client
    created = client.post(
        "/api/projects", json={"name": "Fetch Me"}, headers={"X-CSRF-Token": csrf}
    ).json()
    resp = client.get(f"/api/projects/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Fetch Me"


def test_get_nonexistent_project_404(auth_client):
    client, _csrf = auth_client
    resp = client.get("/api/projects/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_rename_project(auth_client):
    client, csrf = auth_client
    created = client.post(
        "/api/projects", json={"name": "Old Name"}, headers={"X-CSRF-Token": csrf}
    ).json()
    resp = client.patch(
        f"/api/projects/{created['id']}",
        json={"name": "New Name"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_archive_and_unarchive_project(auth_client):
    client, csrf = auth_client
    created = client.post(
        "/api/projects", json={"name": "Cycle"}, headers={"X-CSRF-Token": csrf}
    ).json()

    archived = client.post(
        f"/api/projects/{created['id']}/archive", headers={"X-CSRF-Token": csrf}
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["archived_at"] is not None

    restored = client.post(
        f"/api/projects/{created['id']}/unarchive", headers={"X-CSRF-Token": csrf}
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert restored.json()["archived_at"] is None


def test_duplicate_project(auth_client):
    client, csrf = auth_client
    original = client.post(
        "/api/projects",
        json={"name": "Original", "description": "desc"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    dup = client.post(
        f"/api/projects/{original['id']}/duplicate", headers={"X-CSRF-Token": csrf}
    )
    assert dup.status_code == 201
    assert dup.json()["name"] == "Original (copy)"
    assert dup.json()["description"] == "desc"
    assert dup.json()["id"] != original["id"]


def test_delete_project(auth_client):
    client, csrf = auth_client
    created = client.post(
        "/api/projects", json={"name": "Delete Me"}, headers={"X-CSRF-Token": csrf}
    ).json()
    resp = client.delete(f"/api/projects/{created['id']}", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200

    get_resp = client.get(f"/api/projects/{created['id']}")
    assert get_resp.status_code == 404


def test_projects_require_authentication(client):
    resp = client.get("/api/projects")
    assert resp.status_code == 401


def test_project_ownership_isolation(auth_client, client, email_outbox):
    owner_client, owner_csrf = auth_client
    owned = owner_client.post(
        "/api/projects", json={"name": "Owner's Project"}, headers={"X-CSRF-Token": owner_csrf}
    ).json()

    # A second user cannot see or modify the first user's project.
    import re

    second_password = "Str0ng!Passw0rd"
    client.post(
        "/api/auth/signup",
        json={
            "full_name": "Second User",
            "email": "second@example.com",
            "password": second_password,
            "confirm_password": second_password,
            "accept_terms": True,
        },
    )
    token = re.search(r"token=([A-Za-z0-9_\-]+)", email_outbox[-1].text_body).group(1)
    client.post("/api/auth/verify-email", json={"token": token})
    login_resp = client.post(
        "/api/auth/login", json={"email": "second@example.com", "password": second_password}
    )
    second_csrf = login_resp.cookies["aiagent_csrf"]

    get_resp = client.get(f"/api/projects/{owned['id']}")
    assert get_resp.status_code == 404

    delete_resp = client.delete(
        f"/api/projects/{owned['id']}", headers={"X-CSRF-Token": second_csrf}
    )
    assert delete_resp.status_code == 404
