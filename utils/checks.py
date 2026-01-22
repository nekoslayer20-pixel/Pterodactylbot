import os
from typing import List

def _get_admin_ids() -> List[str]:
    raw = os.getenv("ADMIN_IDS", "")
    return [part.strip() for part in raw.split(",") if part.strip()]

def is_admin_id(user_id: int) -> bool:
    return str(user_id) in _get_admin_ids()

def admin_ids() -> List[int]:
    return [int(x) for x in _get_admin_ids()]
