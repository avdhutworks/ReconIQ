
from uuid import uuid4


def create_source_system_payload(code=None):
    return {
        "code": code or f"TEST_{uuid4().hex[:8]}",
        "name": "Test Payment Gateway",
        "description": "Automated test source system",
    }


def test_create_source_system(client):
    response = client.post(
        "/api/v1/source-systems",
        json={
            "code": "  test_gateway  ",
            "name": "  Test Gateway  ",
            "description": "  Test description  ",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["code"] == "TEST_GATEWAY"
    assert data["name"] == "Test Gateway"
    assert data["description"] == "Test description"
    assert data["is_active"] is True
    assert data["id"] is not None


def test_create_duplicate_source_system_code(client):
    payload = create_source_system_payload("DUPLICATE_TEST")

    first_response = client.post(
        "/api/v1/source-systems",
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = client.post(
        "/api/v1/source-systems",
        json=payload,
    )

    assert second_response.status_code == 409


def test_get_source_system_by_id(client):
    create_response = client.post(
        "/api/v1/source-systems",
        json=create_source_system_payload(),
    )

    source_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/source-systems/{source_id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == source_id


def test_get_nonexistent_source_system(client):
    response = client.get(
        f"/api/v1/source-systems/{uuid4()}"
    )

    assert response.status_code == 404


def test_get_all_source_systems(client):
    client.post(
        "/api/v1/source-systems",
        json=create_source_system_payload(),
    )

    client.post(
        "/api/v1/source-systems",
        json=create_source_system_payload(),
    )

    response = client.get("/api/v1/source-systems")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_update_source_system(client):
    create_response = client.post(
        "/api/v1/source-systems",
        json=create_source_system_payload(),
    )

    source_id = create_response.json()["id"]

    update_payload = {
        "code": "UPDATED_GATEWAY",
        "name": "Updated Payment Gateway",
        "description": "Updated description",
    }

    response = client.put(
        f"/api/v1/source-systems/{source_id}",
        json=update_payload,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["code"] == "UPDATED_GATEWAY"
    assert data["name"] == "Updated Payment Gateway"
    assert data["description"] == "Updated description"


def test_update_source_system_with_duplicate_code(client):
    first = client.post(
        "/api/v1/source-systems",
        json=create_source_system_payload("GATEWAY_ONE"),
    )

    second = client.post(
        "/api/v1/source-systems",
        json=create_source_system_payload("GATEWAY_TWO"),
    )

    second_id = second.json()["id"]

    response = client.put(
        f"/api/v1/source-systems/{second_id}",
        json={
            "code": "GATEWAY_ONE",
            "name": "Another Gateway",
            "description": "Duplicate code test",
        },
    )

    assert response.status_code == 409


def test_deactivate_source_system(client):
    create_response = client.post(
        "/api/v1/source-systems",
        json=create_source_system_payload(),
    )

    source_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/source-systems/{source_id}/deactivate"
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_activate_source_system(client):
    create_response = client.post(
        "/api/v1/source-systems",
        json=create_source_system_payload(),
    )

    source_id = create_response.json()["id"]

    client.patch(
        f"/api/v1/source-systems/{source_id}/deactivate"
    )

    response = client.patch(
        f"/api/v1/source-systems/{source_id}/activate"
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is True


def test_get_active_source_systems_only(client):
    first = client.post(
        "/api/v1/source-systems",
        json=create_source_system_payload(),
    )

    second = client.post(
        "/api/v1/source-systems",
        json=create_source_system_payload(),
    )

    second_id = second.json()["id"]

    client.patch(
        f"/api/v1/source-systems/{second_id}/deactivate"
    )

    response = client.get(
        "/api/v1/source-systems",
        params={"active_only": True},
    )

    assert response.status_code == 200

    source_ids = [
        item["id"] for item in response.json()
    ]

    assert first.json()["id"] in source_ids
    assert second_id not in source_ids


def test_create_source_system_validation(client):
    response = client.post(
        "/api/v1/source-systems",
        json={
            "code": "AB",
            "name": "X",
            "description": None,
        },
    )

    assert response.status_code == 422
