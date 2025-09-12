import re

CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_symbol(value: str) -> str:
    """
    - UTF-8 に再エンコード/デコードして不正シーケンスは無視
    - NUL/制御文字を除去
    - 前後スペース除去
    - 長すぎるものをカット（念のため64文字）
    - 空になったら 'UNK'
    """
    if value is None:
        return "UNK"
    # safety: normalize to str
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:
            return "UNK"
    # drop invalid bytes & control chars
    value = value.encode("utf-8", "ignore").decode("utf-8", "ignore")
    value = CTRL_RE.sub("", value).strip()
    if not value:
        return "UNK"
    if len(value) > 64:
        value = value[:64]
    return value
