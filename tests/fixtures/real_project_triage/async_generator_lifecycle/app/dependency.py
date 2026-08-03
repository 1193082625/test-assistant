async def get_db():
    session = object()
    try:
        yield session
    finally:
        pass


async def broken_get_db():
    try:
        yield object()
    finally:
        raise RuntimeError("production cleanup failed")
