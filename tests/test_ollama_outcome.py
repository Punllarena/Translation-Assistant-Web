from api.ollama.outcome import score


def test_score_used_edited_ignored():
    assert score("She nodded.", "she nodded") == ("used", 1.0)
    assert score("She gave a small nod.", "She gave a small nod, smiling.")[0] == "edited"
    assert score("Rain today.", "The cat slept on the porch all afternoon.")[0] == "ignored"
