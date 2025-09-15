from __future__ import annotations

from typing import Iterable, Optional, Union, Annotated, List
from pydantic.functional_validators import BeforeValidator
from app.lib.utils.convert_id import decode_id


def _normalize_to_iterable(
    v: Union[str, int, Iterable[Union[str, int]]],
) -> Iterable[Union[str, int]]:
    if isinstance(v, (list, tuple, set)):
        return v
    if isinstance(v, str) and "," in v:
        return [item.strip() for item in v.split(",") if item.strip()]
    return [v]


def decode_ids_before(
    v: Optional[Union[str, int, Iterable[Union[str, int]]]],
) -> Optional[list[int]]:
    if v is None:
        return None
    decoded: list[int] = []
    for item in _normalize_to_iterable(v):
        if isinstance(item, int):
            decoded.append(item)
        elif isinstance(item, str) and item.isdigit():
            decoded.append(int(item))
        else:
            decoded.append(decode_id(str(item)))
    return decoded


def decode_id_before(v: Optional[Union[str, int]]) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return decode_id(str(v))


DecodedIDs = Annotated[Optional[list[int]], BeforeValidator(decode_ids_before)]
DecodedID = Annotated[Optional[int], BeforeValidator(decode_id_before)]


def decode_hashid_list(values: Optional[Union[List[str], str]]) -> Optional[list[int]]:
    """
    Decode a list of hashid strings to ints.
    Accepts a list[str] (typical for FastAPI repeated query params) or a
    comma-separated string ("a,b,c").
    """
    if values is None:
        return None
    if isinstance(values, str):
        parts = [p.strip() for p in values.split(",") if p.strip()]
        return [decode_id(p) for p in parts]
    return [decode_id(v) for v in values]
