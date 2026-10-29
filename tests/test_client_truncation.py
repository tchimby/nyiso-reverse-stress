from revstress.agent import client as cl


def _client(replies, **kw):
    """Live-kind client whose transport replays (text, stop_reason) pairs; makes no network call."""
    c = cl.ClaudeClient(max_tokens=100, sleep=lambda s: None, **kw)
    seen = []

    def transport(system, messages):
        text, stop = replies[min(len(seen), len(replies) - 1)]
        seen.append(c.max_tokens)
        c._last_stop_reason = stop
        return text, 10, 5

    c._transport = transport
    return c, seen


def test_truncated_reply_is_retried_with_a_doubled_limit():
    c, seen = _client([("partial", "max_tokens"), ('{"ok": 1}', "end_turn")])
    r = c.complete("s", [{"role": "user", "content": "q"}], "v3")
    assert r.error is None and r.text == '{"ok": 1}' and r.stop_reason == "end_turn"
    assert seen == [100, 200] and c.max_tokens == 200
    assert c.totals["calls"] == 2 and c.totals["output_tokens"] == 10  # the wasted tokens are still counted


def test_growth_stops_at_the_cap_and_returns_the_truncated_text_flagged():
    c, seen = _client([("partial", "max_tokens")], max_tokens_cap=400)
    r = c.complete("s", [{"role": "user", "content": "q"}], "v3")
    assert seen == [100, 200, 400]
    assert r.stop_reason == "max_tokens" and r.text == "partial" and r.error is None


def test_growth_respects_the_call_cap_and_can_be_disabled():
    c, seen = _client([("partial", "max_tokens")], max_total_calls=2)
    r = c.complete("s", [{"role": "user", "content": "q"}], "v3")
    assert len(seen) == 2 and r.error is not None and r.error.startswith("max_total_calls")
    c2, seen2 = _client([("partial", "max_tokens")], grow_on_truncation=False)
    r2 = c2.complete("s", [{"role": "user", "content": "q"}], "v3")
    assert seen2 == [100] and r2.stop_reason == "max_tokens"
