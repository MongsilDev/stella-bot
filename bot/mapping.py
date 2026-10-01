import os
import time
from dataclasses import dataclass, field

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS message_map (
    orig_id INTEGER PRIMARY KEY,
    trans_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    author_name TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL,
    orig_text TEXT NOT NULL DEFAULT '',
    trans_text TEXT NOT NULL DEFAULT '',
    trans_ids TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_message_map_trans ON message_map (trans_id);
"""

# 원문과 번역문을 보관하는 기간. 지나면 그 메시지의 수정과 삭제는 번역에 반영되지 않음
RETENTION_DAYS = 90


@dataclass
class MapRow:
    orig_id: int
    trans_id: int
    channel_id: int
    author_id: int
    direction: str
    author_name: str = ""
    orig_text: str = ""
    trans_text: str = ""
    # 2000자를 넘어 나눠 보낸 번역문의 전체 메시지 ID. trans_id는 첫 조각
    trans_ids: list[int] = field(default_factory=list)

    def chunk_ids(self) -> list[int]:
        return self.trans_ids or [self.trans_id]


class MessageMap:
    _db: aiosqlite.Connection
    _purged_at: float = 0.0

    async def open(self, path: str):
        self._db = await aiosqlite.connect(path)
        os.chmod(path, 0o600)
        await self._db.executescript(SCHEMA)
        cur = await self._db.execute("PRAGMA table_info(message_map)")
        columns = [c[1] for c in await cur.fetchall()]
        for missing in {"author_name", "orig_text", "trans_text", "trans_ids"} - set(columns):
            await self._db.execute(
                f"ALTER TABLE message_map ADD COLUMN {missing} TEXT NOT NULL DEFAULT ''"
            )
        await self._db.commit()
        await self.purge()

    async def purge(self):
        await self._db.execute(
            "DELETE FROM message_map WHERE created_at < datetime('now', ?)", (f"-{RETENTION_DAYS} days",))
        await self._db.commit()
        self._purged_at = time.monotonic()

    async def add(self, row: MapRow):
        if time.monotonic() - self._purged_at > 86400:
            await self.purge()
        await self._db.execute(
            "INSERT OR REPLACE INTO message_map"
            " (orig_id, trans_id, channel_id, author_id, direction, author_name,"
            " orig_text, trans_text, trans_ids)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row.orig_id,
                row.trans_id,
                row.channel_id,
                row.author_id,
                row.direction,
                row.author_name,
                row.orig_text,
                row.trans_text,
                ",".join(map(str, row.trans_ids)),
            ),
        )
        await self._db.commit()

    async def lookup(self, message_id: int) -> MapRow | None:
        cur = await self._db.execute(
            "SELECT orig_id, trans_id, channel_id, author_id, direction, author_name,"
            " orig_text, trans_text, trans_ids"
            " FROM message_map WHERE orig_id = ? OR trans_id = ?",
            (message_id, message_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        ids = [int(x) for x in row[8].split(",") if x]
        return MapRow(*row[:8], trans_ids=ids)

    async def delete(self, orig_id: int):
        await self._db.execute("DELETE FROM message_map WHERE orig_id = ?", (orig_id,))
        await self._db.commit()

    async def close(self):
        await self._db.close()
