"""Public errors never echo submitted credentials or request bodies."""
from fastapi import HTTPException


def invalid(field: str, message: str):
    raise HTTPException(422, [{"loc": ["body", field], "msg": message, "type": "value_error"}])


def public_error(error):
    status = getattr(error, "status", 500)
    detail = getattr(error, "detail", "request failed")
    if status == 422 and not isinstance(detail, list):
        detail = [{"loc": ["body"], "msg": str(detail), "type": "value_error"}]
    return HTTPException(status, detail)
