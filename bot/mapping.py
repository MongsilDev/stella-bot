from dataclasses import dataclass

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS message_map (
    orig_id INTEGER PRIMARY KEY,
    trans_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    author_name TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_message_map_trans ON message_map (trans_id);
"""


@dataclass
class MapRow:
    orig_id: int
    trans_id: int
    channel_id: int
    author_id: int
    direction: str
    author_name: str = ""


class MessageMap:
    _db: aiosqlite.Connection

    async def open(self, path: str):
        self._db = await aiosqlite.connect(path)
        await self._db.executescript(SCHEMA)
        cur = await self._db.execute("PRAGMA table_info(message_map)")
        columns = [c[1] for c in await cur.fetchall()]
        if "author_name" not in columns:
            await self._db.execute(
                "ALTER TABLE message_map ADD COLUMN author_name TEXT NOT NULL DEFAULT ''"
            )
        await self._db.commit()

    async def add(self, row: MapRow):
        await self._db.execute(
            "INSERT OR REPLACE INTO message_map"
            " (orig_id, trans_id, channel_id, author_id, direction, author_name)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                row.orig_id,
                row.trans_id,
                row.channel_id,
                row.author_id,
                row.direction,
                row.author_name,
            ),
        )
        await self._db.commit()

    async def lookup(self, message_id: int) -> MapRow | None:
        cur = await self._db.execute(
            "SELECT orig_id, trans_id, channel_id, author_id, direction, author_name"
            " FROM message_map WHERE orig_id = ? OR trans_id = ?",
            (message_id, message_id),
        )
        row = await cur.fetchone()
        return MapRow(*row) if row else None

    async def delete(self, orig_id: int):
        await self._db.execute("DELETE FROM message_map WHERE orig_id = ?", (orig_id,))
        await self._db.commit()

    async def close(self):
        await self._db.close()
