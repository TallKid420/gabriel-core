from __future__ import annotations


def test_memory_lifecycle(client, auth_headers):
	create_response = client.post(
		"/memory",
		json={"content": "remember this", "metadata": {"scope": "session"}},
		headers=auth_headers,
	)
	assert create_response.status_code == 201
	created = create_response.json()

	list_response = client.get("/memory", headers=auth_headers)
	assert list_response.status_code == 200
	items = list_response.json()["items"]
	assert len(items) == 1
	assert items[0]["content"] == "remember this"

	delete_response = client.delete(f"/memory/{created['id']}", headers=auth_headers)
	assert delete_response.status_code == 200
	assert delete_response.json() == {"deleted": True, "id": created["id"]}

