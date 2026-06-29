from __future__ import annotations


def test_resource_crud_through_command_pipeline(client, auth_headers):
	create_response = client.post(
		"/resources",
		json={
			"resource_type": "tool",
			"resource_id": "summarizer",
			"attributes": {"description": "text summarizer"},
		},
		headers=auth_headers,
	)
	assert create_response.status_code == 201
	resource = create_response.json()
	grn = resource["grn"]
	assert resource["resource_type"] == "tool"

	get_response = client.get(f"/resources/{grn}", headers=auth_headers)
	assert get_response.status_code == 200
	assert get_response.json()["attributes"] == {"description": "text summarizer"}

	update_response = client.patch(
		f"/resources/{grn}",
		json={"attributes": {"description": "updated"}},
		headers=auth_headers,
	)
	assert update_response.status_code == 200
	assert update_response.json()["attributes"] == {"description": "updated"}

	delete_response = client.delete(f"/resources/{grn}", headers=auth_headers)
	assert delete_response.status_code == 200
	assert delete_response.json() == {"deleted": True, "grn": grn}

