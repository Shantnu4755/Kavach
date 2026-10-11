import uuid


def test_create_and_fetch_policy(client):
    resp = client.post(
        "/policies",
        json={"policy_number": "bom-0001", "holder_name": " Test User ", "sum_insured": "500000.00"},
    )
    assert resp.status_code == 201
    policy = resp.get_json()["data"]
    assert policy["policy_number"] == "BOM-0001"
    assert policy["holder_name"] == "Test User"
    assert policy["sum_insured"] == "500000.00"
    assert policy["is_active"] is True

    fetched = client.get(f"/policies/{policy['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["data"]["id"] == policy["id"]


def test_duplicate_policy_number_is_409(client):
    body = {"policy_number": "BOM-0002", "holder_name": "A User", "sum_insured": "1000.00"}
    assert client.post("/policies", json=body).status_code == 201
    resp = client.post("/policies", json=body)
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "conflict"


def test_policy_validation_errors_are_422(client):
    resp = client.post("/policies", json={"policy_number": "X", "holder_name": "A", "sum_insured": "-5"})
    assert resp.status_code == 422
    fields = {e["loc"][0] for e in resp.get_json()["error"]["details"]["errors"]}
    assert fields == {"policy_number", "holder_name", "sum_insured"}


def test_policy_body_must_be_json(client):
    resp = client.post("/policies", data="not json", content_type="text/plain")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["message"] == "Request body must be valid JSON"


def test_unknown_policy_is_404(client):
    assert client.get(f"/policies/{uuid.uuid4()}").status_code == 404


def test_list_policies_newest_first(client):
    for n in range(3):
        body = {"policy_number": f"BOM-10{n}", "holder_name": "User", "sum_insured": "10.00"}
        client.post("/policies", json=body)
    resp = client.get("/policies?limit=2")
    numbers = [p["policy_number"] for p in resp.get_json()["data"]]
    assert numbers == ["BOM-102", "BOM-101"]
