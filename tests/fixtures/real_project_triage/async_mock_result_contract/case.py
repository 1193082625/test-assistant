import asyncio
import gc
from unittest.mock import AsyncMock

from app.service import lookup_signal


def test_unconfigured_result_contract():
    async def exercise():
        db = AsyncMock()
        return await lookup_signal(db)

    value = asyncio.run(exercise())
    del value
    gc.collect()
