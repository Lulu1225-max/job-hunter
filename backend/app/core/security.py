from __future__ import annotations

from uuid import UUID


DEFAULT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def get_current_user_id() -> UUID:
    return DEFAULT_USER_ID
