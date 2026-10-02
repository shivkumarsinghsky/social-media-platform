from fastapi.testclient import TestClient

from social.api import create_app
from social.platform import SocialPlatform
from social.timeline import Strategy


def h(user):
    return {"X-User": user}


def test_post_follow_feed_like_comment_notifications():
    client = TestClient(create_app(SocialPlatform(Strategy.HYBRID, celebrity_threshold=2)))
    assert client.put("/v1/users/bob/follow", headers=h("alice")).json() == {"created": True}
    assert client.put("/v1/users/bob/follow", headers=h("alice")).json() == {"created": False}
    client.put("/v1/users/bob/follow", headers=h("carol"))
    assert client.get("/v1/users/bob").json()["pulledAtReadTime"] is True

    created = [client.post("/v1/posts", json={"text": f"post {i}"}, headers=h("bob")).json() for i in range(3)]
    assert all(isinstance(p["id"], str) for p in created)
    page1 = client.get("/v1/feed", params={"limit": 2}, headers=h("alice")).json()
    assert [p["text"] for p in page1["items"]] == ["post 2", "post 1"]
    page2 = client.get("/v1/feed", params={"limit": 2, "cursor": page1["next"]}, headers=h("alice")).json()
    assert [p["text"] for p in page2["items"]] == ["post 0"] and page2["next"] is None
    ranked = client.get("/v1/feed", params={"mode": "ranked"}, headers=h("alice")).json()
    assert len(ranked["items"]) == 3

    pid = created[0]["id"]
    assert client.put(f"/v1/posts/{pid}/like", headers=h("alice")).json() == {"likes": 1}
    assert client.put(f"/v1/posts/{pid}/like", headers=h("carol")).json() == {"likes": 2}
    assert client.delete(f"/v1/posts/{pid}/like", headers=h("carol")).json() == {"likes": 1}
    assert client.post(f"/v1/posts/{pid}/comments", json={"text": "great @dave"}, headers=h("alice")).status_code == 201
    notes = [n["text"] for n in client.get("/v1/notifications", headers=h("bob")).json()]
    assert notes == [
        "alice commented on your post",
        "carol and 1 other liked your post",
        "carol and 1 other followed you",
    ]
    assert client.get("/v1/notifications", headers=h("dave")).json()[0]["text"] == "alice mentioned you"

    assert client.delete(f"/v1/posts/{pid}", headers=h("alice")).status_code == 403
    assert client.delete(f"/v1/posts/{pid}", headers=h("bob")).status_code == 204
    assert client.get(f"/v1/posts/{pid}").status_code == 404


def test_errors_and_validation():
    client = TestClient(create_app())
    assert client.post("/v1/posts", json={"text": "x"}).status_code == 422  # missing X-User
    assert client.post("/v1/posts", json={"text": "x"}, headers=h("Bad User")).status_code == 422
    assert client.post("/v1/posts", json={"text": "spamlink.example"}, headers=h("bob")).status_code == 422
    assert client.put("/v1/users/bob/follow", headers=h("bob")).status_code == 400
    assert client.get("/v1/feed", params={"cursor": "nope!"}, headers=h("bob")).status_code == 400
    assert client.put("/v1/posts/123/like", headers=h("bob")).status_code == 404
    assert client.get("/v1/posts/abc").status_code == 404
    client.put("/v1/users/bob/block", headers=h("alice"))
    assert client.put("/v1/users/alice/follow", headers=h("bob")).status_code == 403
