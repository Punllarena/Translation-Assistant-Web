from fastapi import Depends

from api.core import nouns, readings
from api.deps import current_user
from api.models import User
from api.routing import api_router
from api.schemas.readings import ReadingsOut, ReadingsRequest, ReadingToken

router = api_router(tags=["readings"])


@router.post("/readings", response_model=ReadingsOut)
def get_readings(body: ReadingsRequest, user: User = Depends(current_user)) -> ReadingsOut:
    try:
        toks = readings.read(body.text)
    except nouns.Unavailable as exc:
        return ReadingsOut(available=False, message=str(exc), tokens=[])
    return ReadingsOut(
        available=True, tokens=[ReadingToken(**t._asdict()) for t in toks]
    )
