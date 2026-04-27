from __future__ import annotations

import pytest

from app.core.clients.model_fetcher import _response_preview

pytestmark = pytest.mark.unit


def test_response_preview_normalizes_whitespace_and_bounds_length() -> None:
    preview = _response_preview("  Forbidden \n request   details  ", max_chars=12)
    assert preview == "Forbidden re"
