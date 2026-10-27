from api.ollama.outcome import score


def test_score_used_edited_ignored():
    assert score("She nodded.", "she nodded") == ("used", 1.0)
    assert score("She gave a small nod.", "She gave a small nod, smiling.")[0] == "edited"
    assert score("Rain today.", "The cat slept on the porch all afternoon.")[0] == "ignored"


def test_long_lightly_edited_line_scores_edited():
    # over 200 characters difflib's autojunk treats common letters as junk (ratio about 0.47)
    base = ("The rain had not stopped since morning, and the old station smelled of wet wool and "
            "coal smoke while the girl waited on the bench with her suitcase, counting the trains "
            "that did not come and wondering whether her brother had forgotten the letter. "
            "When the stationmaster finally walked over and asked where she was going, she only "
            "shook her head and held the ticket tighter, as if someone might take it from her.")
    edited = base
    for old, new in [("had not", "hadn't"), ("did not", "didn't"), ("the ", "a "),
                     ("wondering", "asking herself"), ("finally walked", "at last came"),
                     ("tighter", "more tightly")]:
        edited = edited.replace(old, new)
    verdict, ratio = score(base, edited)
    assert verdict == "edited" and ratio > 0.85
