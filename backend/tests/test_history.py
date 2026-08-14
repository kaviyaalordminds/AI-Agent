from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType
from app.models.user import User


def _seed_entry(db_session, user_id, **overrides):
    defaults = dict(
        user_id=user_id,
        type=HistoryEntryType.image,
        status=HistoryEntryStatus.completed,
        title="A generated image",
    )
    defaults.update(overrides)
    entry = HistoryEntry(**defaults)
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    return entry


def _current_user_id(db_session, email="owner@example.com"):
    return db_session.query(User).filter(User.email == email).first().id


def test_history_empty_for_new_user(auth_client):
    client, _csrf = auth_client
    resp = client.get("/api/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_history_requires_authentication(client):
    resp = client.get("/api/history")
    assert resp.status_code == 401


def test_history_lists_seeded_entries(auth_client, db_session):
    client, _csrf = auth_client
    user_id = _current_user_id(db_session)
    _seed_entry(db_session, user_id, title="Sunset poster")
    _seed_entry(db_session, user_id, title="Landing page", type=HistoryEntryType.website)

    resp = client.get("/api/history")
    body = resp.json()
    assert body["total"] == 2
    titles = {item["title"] for item in body["items"]}
    assert titles == {"Sunset poster", "Landing page"}


def test_history_filter_by_type(auth_client, db_session):
    client, _csrf = auth_client
    user_id = _current_user_id(db_session)
    _seed_entry(db_session, user_id, title="Image one", type=HistoryEntryType.image)
    _seed_entry(db_session, user_id, title="Video one", type=HistoryEntryType.video)

    resp = client.get("/api/history", params={"type": "video"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Video one"


def test_history_filter_by_status(auth_client, db_session):
    client, _csrf = auth_client
    user_id = _current_user_id(db_session)
    _seed_entry(db_session, user_id, title="Failed job", status=HistoryEntryStatus.failed)
    _seed_entry(db_session, user_id, title="Done job", status=HistoryEntryStatus.completed)

    resp = client.get("/api/history", params={"status": "failed"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Failed job"


def test_history_search(auth_client, db_session):
    client, _csrf = auth_client
    user_id = _current_user_id(db_session)
    _seed_entry(db_session, user_id, title="Manufacturing HRMS website")
    _seed_entry(db_session, user_id, title="Marketing poster")

    resp = client.get("/api/history", params={"search": "hrms"})
    body = resp.json()
    assert body["total"] == 1
    assert "HRMS" in body["items"][0]["title"]


def test_history_pagination(auth_client, db_session):
    client, _csrf = auth_client
    user_id = _current_user_id(db_session)
    for i in range(5):
        _seed_entry(db_session, user_id, title=f"Entry {i}")

    resp = client.get("/api/history", params={"page": 1, "page_size": 2})
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 1


def test_history_includes_project_name(auth_client, db_session):
    client, csrf = auth_client
    project = client.post(
        "/api/projects", json={"name": "Linked Project"}, headers={"X-CSRF-Token": csrf}
    ).json()
    user_id = _current_user_id(db_session)
    _seed_entry(db_session, user_id, title="Linked entry", project_id=project["id"])

    resp = client.get("/api/history")
    body = resp.json()
    assert body["items"][0]["project_name"] == "Linked Project"


def test_rename_history_entry(auth_client, db_session):
    client, csrf = auth_client
    user_id = _current_user_id(db_session)
    entry = _seed_entry(db_session, user_id, title="Old title")

    resp = client.patch(
        f"/api/history/{entry.id}",
        json={"title": "New title"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "New title"


def test_move_history_entry_to_project(auth_client, db_session):
    client, csrf = auth_client
    user_id = _current_user_id(db_session)
    entry = _seed_entry(db_session, user_id, title="Movable")
    project = client.post(
        "/api/projects", json={"name": "Target"}, headers={"X-CSRF-Token": csrf}
    ).json()

    resp = client.patch(
        f"/api/history/{entry.id}",
        json={"project_id": project["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["project_name"] == "Target"


def test_delete_history_entry(auth_client, db_session):
    client, csrf = auth_client
    user_id = _current_user_id(db_session)
    entry = _seed_entry(db_session, user_id, title="Delete me")

    resp = client.delete(f"/api/history/{entry.id}", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200

    list_resp = client.get("/api/history")
    assert list_resp.json()["total"] == 0


def test_history_entry_ownership_isolation(auth_client, client, db_session, email_outbox):
    owner_client, _owner_csrf = auth_client
    user_id = _current_user_id(db_session)
    entry = _seed_entry(db_session, user_id, title="Owner's entry")

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
    client.post(
        "/api/auth/login", json={"email": "second@example.com", "password": second_password}
    )

    resp = client.get("/api/history")
    assert resp.json()["total"] == 0

    delete_resp = client.delete(f"/api/history/{entry.id}", headers={"X-CSRF-Token": "x"})
    assert delete_resp.status_code in (403, 404)
