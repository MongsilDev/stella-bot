import pytest

from bot.mapping import MapRow, MessageMap


@pytest.fixture
async def store():
    m = MessageMap()
    await m.open(":memory:")
    yield m
    await m.close()


ROW = MapRow(
    orig_id=100,
    trans_id=200,
    channel_id=1,
    author_id=42,
    direction="KO>JA",
    author_name="몽실",
)


@pytest.mark.asyncio
async def test_lookup_by_orig(store):
    await store.add(ROW)
    assert await store.lookup(100) == ROW


@pytest.mark.asyncio
async def test_lookup_by_trans(store):
    await store.add(ROW)
    assert await store.lookup(200) == ROW


@pytest.mark.asyncio
async def test_lookup_missing_returns_none(store):
    assert await store.lookup(999) is None


@pytest.mark.asyncio
async def test_author_name_roundtrip(store):
    await store.add(ROW)
    found = await store.lookup(100)
    assert found.author_name == "몽실"


@pytest.mark.asyncio
async def test_delete(store):
    await store.add(ROW)
    await store.delete(100)
    assert await store.lookup(100) is None
    assert await store.lookup(200) is None


@pytest.mark.asyncio
async def test_texts_roundtrip(store):
    row = MapRow(
        orig_id=300,
        trans_id=400,
        channel_id=1,
        author_id=42,
        direction="JA>KO",
        author_name="Taro",
        orig_text="今日は21時からで大丈夫ですか？",
        trans_text="오늘 21시부터 시작해도 괜찮으세요?",
    )
    await store.add(row)
    found = await store.lookup(300)
    assert found.orig_text == row.orig_text
    assert found.trans_text == row.trans_text


@pytest.mark.asyncio
async def test_chunk_ids_roundtrip(store):
    row = MapRow(orig_id=500, trans_id=600, channel_id=1, author_id=42,
                 direction="KO>JA", trans_ids=[600, 601, 602])
    await store.add(row)
    found = await store.lookup(500)
    assert found.trans_ids == [600, 601, 602]
    assert found.chunk_ids() == [600, 601, 602]


@pytest.mark.asyncio
async def test_legacy_row_chunk_ids_fall_back_to_first(store):
    await store.add(ROW)
    found = await store.lookup(100)
    assert found.trans_ids == []
    assert found.chunk_ids() == [200]


@pytest.mark.asyncio
async def test_open_migrates_old_schema(tmp_path):
    import aiosqlite
    path = str(tmp_path / "old.db")
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "CREATE TABLE message_map (orig_id INTEGER PRIMARY KEY, trans_id INTEGER NOT NULL,"
            " channel_id INTEGER NOT NULL, author_id INTEGER NOT NULL, direction TEXT NOT NULL)")
        await db.execute("INSERT INTO message_map VALUES (1, 2, 3, 4, 'KO>JA')")
        await db.commit()
    m = MessageMap()
    await m.open(path)
    try:
        found = await m.lookup(1)
        assert found.chunk_ids() == [2]
        await m.add(ROW)
        cur = await m._db.execute("SELECT COUNT(*) FROM message_map WHERE created_at IS NULL")
        assert (await cur.fetchone())[0] == 0
    finally:
        await m.close()
