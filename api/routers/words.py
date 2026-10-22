"""Custom spellcheck words: the account-wide list (series_id NULL) and each series' own."""

from typing import Annotated

from fastapi import Depends, Path, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.deps import current_user, db_session, scoped
from api.models import CustomWord, Series, User
from api.routing import api_router

router = api_router(tags=["words"])

# A dictionary word: no whitespace or slash, at most the column width.
Word = Annotated[str, Path(min_length=1, max_length=120, pattern=r"^[^\s/]+$")]


def _in_list(user_id: int, series_id: int | None):
    """The WHERE clause selecting one list's rows."""
    if series_id is None:
        return (CustomWord.user_id == user_id) & CustomWord.series_id.is_(None)
    return CustomWord.series_id == series_id


def _list(db: Session, user_id: int, series_id: int | None) -> list[str]:
    return list(
        db.scalars(
            select(CustomWord.word)
            .where(_in_list(user_id, series_id))
            .order_by(func.lower(CustomWord.word), CustomWord.word)
        )
    )


def _add(db: Session, user_id: int, series_id: int | None, word: str) -> None:
    """Idempotent: a word already present in any letter case is left as it is. No conflict
    target, so whichever partial unique index applies to the row does the work."""
    db.execute(
        insert(CustomWord)
        .values(user_id=user_id, series_id=series_id, word=word)
        .on_conflict_do_nothing()
    )


def _remove(db: Session, user_id: int, series_id: int | None, word: str) -> None:
    db.execute(
        delete(CustomWord).where(
            _in_list(user_id, series_id), func.lower(CustomWord.word) == word.lower()
        )
    )


@router.get("/words", response_model=list[str])
def list_account_words(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[str]:
    return _list(db, user.id, None)


@router.put("/words/{word}", status_code=status.HTTP_204_NO_CONTENT)
def add_account_word(
    word: Word, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    _add(db, user.id, None, word)


@router.delete("/words/{word}", status_code=status.HTTP_204_NO_CONTENT)
def remove_account_word(
    word: Word, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    _remove(db, user.id, None, word)


@router.get("/series/{series_id}/words", response_model=list[str])
def list_series_words(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[str]:
    return _list(db, user.id, scoped(db, Series, series_id, user.id).id)


@router.put("/series/{series_id}/words/{word}", status_code=status.HTTP_204_NO_CONTENT)
def add_series_word(
    series_id: int,
    word: Word,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> None:
    _add(db, user.id, scoped(db, Series, series_id, user.id).id, word)


@router.delete("/series/{series_id}/words/{word}", status_code=status.HTTP_204_NO_CONTENT)
def remove_series_word(
    series_id: int,
    word: Word,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> None:
    _remove(db, user.id, scoped(db, Series, series_id, user.id).id, word)
