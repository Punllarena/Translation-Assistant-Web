from api.ollama.chunks import Item
from api.ollama.prompt import (
    FORMAT_RULES,
    build_messages,
    estimate_tokens,
    num_ctx,
    request_ctx,
    steady_ctx,
)


def test_messages_mark_context_done_and_dollar_lines():
    m = build_messages("You translate {src} to {dst}.", "ja", "en",
                       [Item(1, "%", "前", "Before")],
                       [Item(2, "%", "猫"), Item(3, "$", "犬"), Item(4, "%", "鳥", "Bird")])
    # api.mt.languages.display adds the code, as the existing MT backend does
    assert m[0]["content"].startswith("You translate Japanese (ja) to English (en).")
    assert m[0]["content"].endswith(FORMAT_RULES)
    assert "[1] 前 => Before" in m[1]["content"]
    assert "[3]$ 犬" in m[1]["content"] and "[4] 鳥 (done) => Bird" in m[1]["content"]


def test_no_context_section_when_empty():
    m = build_messages("s", "ja", "en", [], [Item(2, "%", "猫")])
    assert m[1]["content"] == "Translate:\n[2] 猫"


def test_estimate_tokens():
    assert estimate_tokens("abcde") == 2
    assert estimate_tokens("猫猫a") == 3


def test_num_ctx_rounds_up_and_has_a_floor():
    assert num_ctx([{"content": "a"}], 1) == 2048
    assert num_ctx([{"content": "猫" * 3000}], 10) % 1024 == 0


def test_steady_ctx_is_a_power_of_two_from_the_preset():
    small = steady_ctx("You translate {src} to {dst}.", 12, 5)
    medium = steady_ctx("You translate {src} to {dst}.", 25, 10)
    assert small == 4096 and medium == 8192
    assert steady_ctx("s", 0, 0) == 2048  # whole chapter: sized by the chapter instead
    # the same prefs always give the same value
    assert steady_ctx("s", 12, 5) == steady_ctx("s", 12, 5)
    assert steady_ctx("s" * 40000, 12, 5) == 16384


def test_request_ctx_keeps_steady_grows_and_clamps():
    assert request_ctx(4096, 3000, None) == 4096  # fits: no change, no reload
    assert request_ctx(4096, 5000, None) == 8192  # grows to the next power of two
    assert request_ctx(8192, 3000, None) == 8192  # never steps down
    assert request_ctx(8192, 3000, 6000) == 6000  # clamped to the model's context length
