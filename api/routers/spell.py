from typing import Annotated

from fastapi import Depends, Path, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.core import spell
from api.deps import current_user, db_session, owned_ref, scoped
from api.models import CustomWord, Profile, User
from api.routing import api_router
from api.schemas.spell import Misspelling, SpellRequest, SpellResult

router = api_router(tags=["spell"])

# suggest() runs under a global lock at ~2 ms a call; bound what one request can cost.
MAX_SUGGESTED_WORDS = 100

# A dictionary word: no whitespace or slash, at most the column width.
Word = Annotated[str, Path(min_length=1, max_length=120, pattern=r"^[^\s/]+$")]


@router.post("/spell/check", response_model=SpellResult)
def check(
    body: SpellRequest, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> SpellResult:
    custom: set[str] = set()
    if body.profile_id is not None:
        profile = owned_ref(db, Profile, body.profile_id, user.id, "profile_id")
        custom = {
            w.lower()
            for w in db.scalars(select(CustomWord.word).where(CustomWord.profile_id == profile.id))
        }
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


@router.get("/profiles/{profile_id}/words", response_model=list[str])
def list_words(
    profile_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[str]:
    profile = scoped(db, Profile, profile_id, user.id)
    return list(
        db.scalars(
            select(CustomWord.word)
            .where(CustomWord.profile_id == profile.id)
            .order_by(func.lower(CustomWord.word))
        )
    )


@router.put("/profiles/{profile_id}/words/{word}", status_code=status.HTTP_204_NO_CONTENT)
def add_word(
    profile_id: int,
    word: Word,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> None:
    """Idempotent: a word already present in any letter case is left as it is."""
    profile = scoped(db, Profile, profile_id, user.id)
    db.execute(
        insert(CustomWord).values(profile_id=profile.id, word=word).on_conflict_do_nothing()
    )


@router.delete("/profiles/{profile_id}/words/{word}", status_code=status.HTTP_204_NO_CONTENT)
def remove_word(
    profile_id: int,
    word: Word,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> None:
    profile = scoped(db, Profile, profile_id, user.id)
    db.execute(
        delete(CustomWord).where(
            CustomWord.profile_id == profile.id, func.lower(CustomWord.word) == word.lower()
        )
    )
