from fastapi import Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.core import spell
from api.deps import current_user, db_session, owned_ref
from api.models import CustomWord, Series, User
from api.routing import api_router
from api.schemas.spell import Misspelling, SpellRequest, SpellResult

router = api_router(tags=["spell"])

# suggest() runs under a global lock at ~2 ms a call; bound what one request can cost.
MAX_SUGGESTED_WORDS = 100


@router.post("/spell/check", response_model=SpellResult)
def check(
    body: SpellRequest, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> SpellResult:
    # The account-wide list plus, when a series is named, that series' own list.
    in_series = CustomWord.series_id.is_(None)
    if body.series_id is not None:
        series = owned_ref(db, Series, body.series_id, user.id, "series_id")
        in_series = or_(in_series, CustomWord.series_id == series.id)
    custom = set(
        db.scalars(
            select(func.lower(CustomWord.word)).where(CustomWord.user_id == user.id, in_series)
        )
    )
    d = spell.dictionary()
    if d is None:
        return SpellResult(available=False, results=[[] for _ in body.texts])
    suggestions: dict[str, list[str]] = {}  # suggest() is the slow call; once per word
    results = []
    for text in body.texts:
        spans = []
        for start, end, word in spell.misspellings(text, custom, d):
            if word not in suggestions:
                suggestions[word] = (
                    spell.suggest(d, word) if len(suggestions) < MAX_SUGGESTED_WORDS else []
                )
            spans.append(
                Misspelling(start=start, end=end, word=word, suggestions=suggestions[word])
            )
        results.append(spans)
    return SpellResult(available=True, results=results)
