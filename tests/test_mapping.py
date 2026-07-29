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
