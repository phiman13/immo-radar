def test_docs_reachable(client):
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_api_404(client):
    resp = client.get("/api/nonexistent")
    assert resp.status_code == 404
