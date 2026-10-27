from api.ollama.prefs import OllamaPrefs, parse


def test_default_is_small_preset():
    assert parse({}) == OllamaPrefs("small", 12, 5, None)


def test_preset_numbers_win_over_stored_numbers():
    assert parse({"ollama_preset": "medium", "ollama_chunk_lines": 3}).chunk_lines == 25


def test_custom_reads_numbers_and_rejects_bad_shapes():
    assert parse({"ollama_preset": "custom", "ollama_chunk_lines": 40, "ollama_context_lines": 8}) \
        == OllamaPrefs("custom", 40, 8, None)
    assert parse({"ollama_preset": "custom", "ollama_chunk_lines": "x"}).chunk_lines == 12
    assert parse({"ollama_preset": "custom", "ollama_chunk_lines": True}).chunk_lines == 12


def test_large_is_whole_chapter_and_num_thread_bounds():
    assert parse({"ollama_preset": "large"}).chunk_lines == 0
    assert parse({"ollama_num_thread": 4}).num_thread == 4
    assert parse({"ollama_num_thread": 0}).num_thread is None
