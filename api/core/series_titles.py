"""Series title helpers; pure so the migration can import them without the models."""


def free_title(taken: set[str], title: str) -> str:
    """``title``, or ``"title (2)"``, ``"title (3)"``... the first not in ``taken``."""
    if title not in taken:
        return title
    n = 2
    while f"{title} ({n})" in taken:
        n += 1
    return f"{title} ({n})"


def free_glossary_title(taken: set[str], base: str) -> str:
    """``base``, else ``base (glossary)``, else ``base (glossary 2)``, ``(glossary 3)``...:
    the first whose lower case is not in ``taken`` (lower-cased titles). A desktop profile
    kept as its own series is titled this way; the series_glossary migration has its own
    copy of the rule."""
    candidate, n = base, 2
    if candidate.lower() in taken:
        candidate = f"{base} (glossary)"
    while candidate.lower() in taken:
        candidate, n = f"{base} (glossary {n})", n + 1
    return candidate
