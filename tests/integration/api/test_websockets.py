import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import USER_ID

@pytest.mark.asyncio
async def test_websocket_auth_success(authenticated_client: TestClient):
    """Tests successful WebSocket connection with valid auth and ownership."""
    # 1. Create a review to connect to
    main_room_res = authenticated_client.post("/api/rooms", json={"name": "Main for WS", "type": "main"})
    main_room_id = main_room_res.json()["room_id"]
    sub_room_res = authenticated_client.post("/api/rooms", json={"name": "Sub for WS", "type": "sub", "parent_id": main_room_id})
    sub_room_id = sub_room_res.json()["room_id"]
    review_res = authenticated_client.post(
        f"/api/rooms/{sub_room_id}/reviews",
        json={"topic": "WS Test", "instruction": "Test"}
    )
    review_id = review_res.json()["review_id"]

    # 2. The authenticated_client fixture provides the token via headers,
    # but for WebSockets we need to pass it as a subprotocol.
    # We can get the token from the client's headers.
    token = authenticated_client.headers["Authorization"].split(" ")[1]

    with authenticated_client.websocket_connect(f"/ws/reviews/{review_id}", subprotocols=["graphql-ws", token]) as websocket:
        # If we connect successfully, the test passes.
        # We can optionally receive a confirmation message if the protocol defines one.
        # For now, just connecting is enough.
        websocket.close()

@pytest.mark.asyncio
async def test_websocket_auth_failure_bad_token(client: TestClient):
    """Tests that WebSocket connection is rejected with a bad token."""
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/reviews/some_review_id", subprotocols=["graphql-ws", "bad-token"]):
            pass # Should not get here
    assert excinfo.value.code == 1008

@pytest.mark.asyncio
async def test_websocket_auth_failure_wrong_owner(authenticated_client: TestClient):
    """Tests that a user cannot connect to a review they do not own."""
    # 1. Create a review with the default user
    main_room_res = authenticated_client.post("/api/rooms", json={"name": "Main for WS Owner Test", "type": "main"})
    main_room_id = main_room_res.json()["room_id"]
    sub_room_res = authenticated_client.post("/api/rooms", json={"name": "Sub for WS Owner Test", "type": "sub", "parent_id": main_room_id})
    sub_room_id = sub_room_res.json()["room_id"]
    review_res = authenticated_client.post(
        f"/api/rooms/{sub_room_id}/reviews",
        json={"topic": "WS Owner Test", "instruction": "Test"}
    )
    review_id = review_res.json()["review_id"]

    # 2. Attempt to connect as a different user
    with patch("firebase_admin.auth.verify_id_token") as mock_verify_token:
        mock_verify_token.return_value = {"uid": "other-user"}
        token = "mocked-token-for-other-user"

        with pytest.raises(WebSocketDisconnect) as excinfo:
            with authenticated_client.websocket_connect(f"/ws/reviews/{review_id}", subprotocols=["graphql-ws", token]):
                pass

    assert excinfo.value.code == 1008
