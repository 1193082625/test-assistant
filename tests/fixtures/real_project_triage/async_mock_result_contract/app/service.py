async def lookup_signal(db):
    result = await db.execute("select signal")
    return result.scalar_one_or_none()


async def broken_lookup_signal(db):
    result = db.execute("select signal")
    return result.scalar_one_or_none()
