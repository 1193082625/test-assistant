import asyncio
import gc

from app.dependency import get_db


def test_get_db_yields_session():
    async def exercise():
        generator = get_db()
        return generator.__anext__()

    session = asyncio.run(exercise())
    del session
    gc.collect()
