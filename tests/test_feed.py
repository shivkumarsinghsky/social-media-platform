import pytest

from social.ids import IdGenerator, timestamp_ms
from social.platform import ModerationError, SocialPlatform
from social.posts import Visibility
from social.simulation import run
from social.timeline import Strategy, TimelineCache, decode_cursor, encode_cursor


def platform(strategy=Strategy.HYBRID, threshold=3):
    p = SocialPlatform(strategy, celebrity_threshold=threshold)
    for u in ["alice", "bob", "carol", "dave", "erin", "star"]:
        p.register(u)
    for fan in ["alice", "bob", "carol"]:
        p.follow(fan, "star")  # star reaches the threshold → pulled at read time
    p.follow("alice", "bob")
    return p


def ids(page):
    return [p.text for p in page.posts]


def test_ids_are_time_ordered_and_monotonic_even_if_clock_goes_back():
    t = [1_800_000_000_000]
    gen = IdGenerator(5, clock=lambda: t[0])
    a = gen.next_id()
    t[0] -= 1000  # clock skew
    b = gen.next_id()
    assert b > a and timestamp_ms(a) == 1_800_000_000_000
    with pytest.raises(ValueError):
        IdGenerator(5000)


@pytest.mark.parametrize("strategy", list(Strategy))
def test_all_strategies_return_the_same_chronological_feed(strategy):
    p = platform(strategy)
    p.post("bob", "b1")
    p.post("star", "s1")
    p.post("alice", "a1")
    p.post("dave", "d1")  # alice does not follow dave
    p.post("star", "s2")
    assert ids(p.feed.chronological("alice", None, 10)) == ["s2", "a1", "s1", "b1"]


def test_hybrid_pushes_normal_authors_and_pulls_celebrities():
    p = platform(Strategy.HYBRID)
    assert p.feed.fan_out(p.posts.create("bob", "x")) == 2  # bob's own timeline + follower alice
    assert p.feed.fan_out(p.posts.create("star", "y")) == 1  # only star's own timeline
    assert p.feed.is_pull_author("star") and not p.feed.is_pull_author("bob")


def test_cursor_pagination_is_stable_while_new_posts_arrive():
    p = platform()
    for i in range(5):
        p.post("bob", f"b{i}")
        p.post("star", f"s{i}")
    first = p.feed.chronological("alice", None, 4)
    assert ids(first) == ["s4", "b4", "s3", "b3"]
    p.post("bob", "new")  # does not shift the next page
    second = p.feed.chronological("alice", first.next_cursor, 4)
    assert ids(second) == ["s2", "b2", "s1", "b1"]
    last = p.feed.chronological("alice", second.next_cursor, 4)
    assert ids(last) == ["s0", "b0"] and last.next_cursor is None
    with pytest.raises(ValueError):
        decode_cursor("garbage!")
    assert decode_cursor(encode_cursor(42)) == 42


def test_cold_timeline_is_rebuilt_on_read():
    p = platform()
    p.post("bob", "b1")
    p.cache.evict("alice")  # e.g. inactive user evicted from the cache
    p.post("bob", "b2")  # fan-out skips users without a cached timeline
    page = p.feed.chronological("alice", None, 10)
    assert page.rebuilt and ids(page)[:2] == ["b2", "b1"]


def test_unfollow_block_and_delete_are_respected_at_read_time():
    p = platform()
    b = p.post("bob", "b1")
    p.post("star", "s1")
    p.graph.unfollow("alice", "bob")
    assert ids(p.feed.chronological("alice", None, 10)) == ["s1"]
    p.follow("alice", "bob")
    p.posts.delete(b.id, "bob")
    assert ids(p.feed.chronological("alice", None, 10)) == ["s1"]
    p.graph.block("alice", "star")
    assert ids(p.feed.chronological("alice", None, 10)) == []
    with pytest.raises(PermissionError):
        p.follow("star", "alice")


def test_follow_backfills_recent_posts():
    p = platform()
    p.post("dave", "d1")
    p.follow("alice", "dave")
    assert "d1" in ids(p.feed.chronological("alice", None, 10))


def test_timeline_cache_is_bounded_and_idempotent():
    c = TimelineCache(max_size=3)
    for i in [1, 2, 2, 3, 4]:
        c.insert("u", i)
    assert c.page("u", None, 10) == [4, 3, 2] and c.page("u", 3, 10) == [2]


def test_ranked_feed_prefers_engagement_among_recent_posts():
    p = platform()
    quiet = p.post("bob", "quiet")
    popular = p.post("bob", "popular")
    newest = p.post("bob", "newest")
    for u in ["carol", "dave", "erin"]:
        p.like(quiet.id, u)
    now = popular.created_ms + 3_600_000
    ranked = [x.text for x in p.feed.ranked("alice", now, 3)]
    assert ranked[0] == "quiet" and set(ranked) == {quiet.text, popular.text, newest.text}


def test_notifications_aggregate_likes_and_handle_mentions():
    p = platform()
    post = p.post("alice", "hi @bob and @carol")
    for u in ["bob", "carol", "dave"]:
        p.like(post.id, u)
    p.like(post.id, "bob")  # repeated like: no change
    p.comment(post.id, "dave", "nice @erin")
    texts = [n.summary() for n in p.notifications.list("alice")]
    assert texts == ["dave commented on your post", "dave and 2 others liked your post"]
    assert [n.summary() for n in p.notifications.list("star")] == ["carol and 2 others followed you"]
    assert [n.summary() for n in p.notifications.list("bob")] == ["alice mentioned you", "alice followed you"]
    assert [n.summary() for n in p.notifications.list("erin")] == ["dave mentioned you"]
    assert ("alice", "dave commented on your post") in p.notifications.push_outbox


def test_moderation_rejects_policy_violations_and_hides_reported_posts():
    p = platform()
    with pytest.raises(ModerationError):
        p.post("bob", "visit spamlink.example now")
    post = p.post("bob", "borderline")
    for reporter in ["carol", "carol", "dave"]:
        assert p.moderator.report(post, reporter) is False
    assert p.moderator.report(post, "erin") is True and post.visibility is Visibility.HIDDEN
    assert post.id in p.moderator.review_queue
    assert "borderline" not in ids(p.feed.chronological("alice", None, 10))


def test_simulation_shows_the_fan_out_trade_off():
    by = {r.strategy: r for r in run(users=800, threshold=80, posts=300, reads=100)}
    w, r, h = by[Strategy.WRITE], by[Strategy.READ], by[Strategy.HYBRID]
    assert r.writes_per_post_avg == 0 and w.sources_per_read_max == 1
    assert h.writes_per_post_max <= 80  # bounded by the threshold (+ the author's own timeline)
    assert h.writes_per_post_avg < w.writes_per_post_avg and h.sources_per_read_avg < r.sources_per_read_avg
