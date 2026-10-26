from api.ollama.chunks import Item
from api.ollama.prompt import FORMAT_RULES, build_messages, estimate_tokens, num_ctx


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
