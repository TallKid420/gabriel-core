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


def test_list_resources_uses_materialized_read_model(client, auth_headers):
	first = client.post(
		"/resources",
		json={
			"resource_type": "tool",
			"resource_id": "projection-tool-1",
			"attributes": {"name": "first"},
		},
		headers=auth_headers,
	)
	second = client.post(
		"/resources",
		json={
			"resource_type": "workflow",
			"resource_id": "projection-workflow-1",
			"attributes": {"name": "second"},
		},
		headers=auth_headers,
	)
	assert first.status_code == 201
	assert second.status_code == 201

	list_response = client.get("/resources", headers=auth_headers)
	assert list_response.status_code == 200
	items = list_response.json()["items"]
	grns = {item["grn"] for item in items}
	assert first.json()["grn"] in grns
	assert second.json()["grn"] in grns

	filtered = client.get("/resources?resource_type=tool", headers=auth_headers)
	assert filtered.status_code == 200
	filtered_items = filtered.json()["items"]
	assert len(filtered_items) >= 1
	assert all(item["resource_type"] == "tool" for item in filtered_items)


def test_list_resources_excludes_deleted_by_default(client, auth_headers):
	create_response = client.post(
		"/resources",
		json={
			"resource_type": "tool",
			"resource_id": "projection-delete-check",
			"attributes": {"name": "to-delete"},
		},
		headers=auth_headers,
	)
	assert create_response.status_code == 201
	grn = create_response.json()["grn"]

	delete_response = client.delete(f"/resources/{grn}", headers=auth_headers)
	assert delete_response.status_code == 200

	list_response = client.get("/resources", headers=auth_headers)
	assert list_response.status_code == 200
	items = list_response.json()["items"]
	assert all(item["grn"] != grn for item in items)

	include_deleted = client.get("/resources?include_deleted=true", headers=auth_headers)
	assert include_deleted.status_code == 200
	deleted_items = include_deleted.json()["items"]
	assert any(item["grn"] == grn and item["state"] == "deleted" for item in deleted_items)

