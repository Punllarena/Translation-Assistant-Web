"""Series title helpers; pure so the migration can import them without the models."""


def free_title(taken: set[str], title: str) -> str:
    """``title``, or ``"title (2)"``, ``"title (3)"``... the first not in ``taken``."""
    if title not in taken:
        return title
    n = 2
    while f"{title} ({n})" in taken:
        n += 1
    return f"{title} ({n})"
