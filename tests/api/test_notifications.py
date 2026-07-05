from __future__ import annotations


def test_get_notifications_returns_notification_list(client, auth_headers):
	response = client.get("/notifications", headers=auth_headers)
	assert response.status_code == 200, response.text

	items = response.json()
	assert isinstance(items, list)
	assert len(items) > 0

	first = items[0]
	assert "grn" in first
	assert "level" in first
	assert "title" in first
	assert "body" in first
	assert "created_at" in first
	assert isinstance(first["read"], bool)


def test_change_notification_read_status_accepts_grn_path(client, auth_headers):
	notification_grn = "grn:organization:notification/chat:1"
	response = client.patch(f"/notifications/{notification_grn}", headers=auth_headers)
	assert response.status_code == 200, response.text

	body = response.json()
	assert body["ok"] is True
	assert notification_grn in body["detail"]
