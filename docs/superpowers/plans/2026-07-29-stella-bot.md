# 스텔라봇 (stella-bot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Discord 채널 1개에서 KO↔JA 실시간 상호 번역 봇 구현.

**Architecture:** 단일 프로세스 discord.py 봇. on_message에서 언어 감지 → 마스킹 → DeepL 번역 → 웹훅(작성자 닉네임·아바타)으로 게시. 원본↔번역 메시지 ID를 SQLite에 매핑해 리플라이 인용줄·수정·삭제 동기화를 처리한다.

**Tech Stack:** Python 3.12, discord.py>=2.7.1, httpx, aiosqlite, python-dotenv, sentry-sdk, pytest + pytest-asyncio, DeepL API Free.

## Global Constraints

- discord.py >= 2.7.1
- 번역 엔진은 DeepL API Free만 사용. Free 키(`:fx` 접미사) → `https://api-free.deepl.com`
- 번역문은 웹훅으로 게시하며 `allowed_mentions=none` 고정
- 대상 채널은 env `CHANNEL_ID` 1개
- `.env`, `data/`는 절대 커밋하지 않는다
- 커밋 메시지: `<type>: 한국어 설명`, Claude-Session 트레일러 금지
- 모든 소스 파일은 `bot/` 패키지, 테스트는 `tests/`

## File Structure

```
stella-bot/
├── main.py               # 엔트리: env 로드, Sentry init, StellaBot 실행
├── bot/
│   ├── __init__.py
│   ├── detect.py         # 언어 감지 휴리스틱 (순수 함수)
│   ├── masking.py        # 이모지·멘션·코드·URL 마스킹/복원 (순수 함수)
│   ├── formatting.py     # 인용줄·점프링크·2000자 분할 (순수 함수)
│   ├── translator.py     # DeepL httpx 클라이언트 (재시도·456 처리)
│   ├── mapping.py        # aiosqlite message_map 저장소
│   └── client.py         # StellaBot(discord.Client): 이벤트·웹훅·파이프라인
├── tests/
│   ├── test_detect.py
│   ├── test_masking.py
│   ├── test_formatting.py
│   ├── test_translator.py
│   └── test_mapping.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

Task 1이 스캐폴드를 포함한다. Task 2~5(masking, formatting, translator, mapping)는 서로 독립 — 병렬 실행 가능. Task 6(client)이 전부 소비. Task 7 라이브 스모크, Task 8 GitHub 배포.

---

### Task 1: 스캐폴드 + 언어 감지 (bot/detect.py)

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`, `README.md`, `bot/__init__.py`, `bot/detect.py`
- Test: `tests/test_detect.py`

**Interfaces:**
- Produces: `detect_direction(text: str) -> tuple[str, str] | None` — `("KO","JA")` / `("JA","KO")` / 스킵이면 `None`

- [ ] **Step 1: 스캐폴드 파일 작성**

`requirements.txt`:
```
discord.py>=2.7.1
httpx>=0.27
aiosqlite>=0.20
python-dotenv>=1.0
sentry-sdk>=2.0
pytest>=8.0
pytest-asyncio>=0.23
```

`.gitignore`:
```
__pycache__/
*.pyc
.env
data/
.venv/
.pytest_cache/
```

`.env.example`:
```
DISCORD_TOKEN=
DEEPL_API_KEY=
CHANNEL_ID=
SENTRY_DSN=
```

`README.md`:
```markdown
# 스텔라봇 (stella-bot)

Discord 채널 1개에서 한국어·일본어 사용자가 자유롭게 대화하도록 실시간 상호 번역을 해주는 봇.
번역문은 원 작성자의 닉네임·아바타로 표시되고, 답장 관계·수정·삭제가 번역문에 그대로 반영된다.

## 실행 방법

1. `.env.example`을 `.env`로 복사하고 값을 채운다
2. 의존성 설치: `pip install -r requirements.txt`
3. 실행: `python main.py`

봇에게 대상 채널의 메시지 보기·메시지 기록·웹훅 관리 권한이 필요하다.

## 테스트

pytest
```

`bot/__init__.py`: 빈 파일.

- [ ] **Step 2: 실패하는 테스트 작성** — `tests/test_detect.py`

```python
from bot.detect import detect_direction


def test_korean_to_japanese():
    assert detect_direction("오늘 스크림 몇 시에 해요?") == ("KO", "JA")


def test_japanese_to_korean():
    assert detect_direction("今日のスクリムは何時ですか") == ("JA", "KO")


def test_kana_only():
    assert detect_direction("おはよう") == ("JA", "KO")


def test_kanji_only_treated_as_japanese():
    assert detect_direction("了解") == ("JA", "KO")


def test_mixed_hangul_dominant():
    assert detect_direction("아 그거 ね 진짜 웃겼음 ㅋㅋ") == ("KO", "JA")


def test_mixed_kana_dominant():
    assert detect_direction("それなーww 인정") == ("JA", "KO")


def test_english_skipped():
    assert detect_direction("gg wp") is None


def test_empty_skipped():
    assert detect_direction("") is None


def test_emoji_only_skipped():
    assert detect_direction("👍🔥") is None
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_detect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.detect'`

- [ ] **Step 4: 구현** — `bot/detect.py`

```python
import re

HANGUL = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")
KANA = re.compile(r"[぀-ゟ゠-ヿ]")
HAN = re.compile(r"[一-鿿]")


def detect_direction(text: str) -> tuple[str, str] | None:
    """한글·가나 문자 수로 원문 언어를 판정한다. 한자만 있으면 일본어로 간주."""
    hangul = len(HANGUL.findall(text))
    kana = len(KANA.findall(text))
    if hangul and kana:
        return ("KO", "JA") if hangul >= kana else ("JA", "KO")
    if hangul:
        return ("KO", "JA")
    if kana:
        return ("JA", "KO")
    if HAN.search(text):
        return ("JA", "KO")
    return None
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/test_detect.py -v`
Expected: PASS (9개)

- [ ] **Step 6: 커밋 (스캐폴드와 감지 분리)**

```bash
git add requirements.txt .gitignore .env.example README.md bot/__init__.py
git commit -m "chore: 프로젝트 스캐폴드 구성"
git add bot/detect.py tests/test_detect.py
git commit -m "feat: 한일 언어 감지 휴리스틱 추가"
```

---

### Task 2: 마스킹/복원 (bot/masking.py)

**Files:**
- Create: `bot/masking.py`
- Test: `tests/test_masking.py`

**Interfaces:**
- Produces: `mask(text: str) -> tuple[str, list[str]]` — 보존 구간을 `<x i="N"/>`로 치환, 원본 구간 리스트 반환
- Produces: `unmask(text: str, spans: list[str]) -> str` — 토큰을 원본으로 복원 (DeepL이 넣는 공백 변형 `<x i="0" />` 허용)
- 보존 대상: 코드블록, 인라인코드, 커스텀 이모지 `<a?:name:id>`, 멘션 `<@id> <@!id> <@&id>`, 채널 `<#id>`, URL
- DeepL 호출 시 `tag_handling=xml`, `ignore_tags=["x"]`와 함께 쓰는 전제

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_masking.py`

```python
from bot.masking import mask, unmask


def test_custom_emoji_preserved():
    masked, spans = mask("안녕 <:wave:1234567890>")
    assert "<:wave:" not in masked
    assert unmask(masked, spans) == "안녕 <:wave:1234567890>"


def test_mention_and_channel_preserved():
    src = "<@123> <#456> 여기로 와요 <@&789>"
    masked, spans = mask(src)
    assert "@" not in masked and "#" not in masked
    assert unmask(masked, spans) == src


def test_code_block_preserved():
    src = "이거 봐 ```py\nprint('hi')\n``` 어때"
    masked, spans = mask(src)
    assert "print" not in masked
    assert unmask(masked, spans) == src


def test_inline_code_preserved():
    src = "`git rebase` 하면 돼요"
    masked, spans = mask(src)
    assert "git" not in masked
    assert unmask(masked, spans) == src


def test_url_preserved():
    src = "여기 https://example.com/길고?긴=주소 참고"
    masked, spans = mask(src)
    assert "example.com" not in masked
    assert unmask(masked, spans) == src


def test_unmask_tolerates_deepl_spacing():
    _, spans = mask("<@123> 안녕")
    assert unmask('<x i="0" /> 안녕', spans) == "<@123> 안녕"


def test_no_special_content_passthrough():
    masked, spans = mask("그냥 평범한 문장")
    assert masked == "그냥 평범한 문장"
    assert spans == []


def test_index_out_of_range_left_asis():
    assert unmask('<x i="9"/>', []) == '<x i="9"/>'
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_masking.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현** — `bot/masking.py`

```python
import re

PRESERVE = re.compile(
    r"```.*?```"
    r"|`[^`\n]+`"
    r"|<a?:\w+:\d+>"
    r"|<@!?\d+>|<@&\d+>|<#\d+>"
    r"|https?://\S+",
    re.S,
)
TOKEN = re.compile(r'<x i="(\d+)"\s*/>')


def mask(text: str) -> tuple[str, list[str]]:
    spans: list[str] = []

    def repl(m: re.Match) -> str:
        spans.append(m.group(0))
        return f'<x i="{len(spans) - 1}"/>'

    return PRESERVE.sub(repl, text), spans


def unmask(text: str, spans: list[str]) -> str:
    def repl(m: re.Match) -> str:
        i = int(m.group(1))
        return spans[i] if i < len(spans) else m.group(0)

    return TOKEN.sub(repl, text)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_masking.py -v`
Expected: PASS (8개)

- [ ] **Step 5: 커밋**

```bash
git add bot/masking.py tests/test_masking.py
git commit -m "feat: 이모지·멘션·코드·URL 마스킹/복원 추가"
```

---

### Task 3: 포맷 유틸 (bot/formatting.py)

**Files:**
- Create: `bot/formatting.py`
- Test: `tests/test_formatting.py`

**Interfaces:**
- Produces: `build_reply_line(name: str, url: str) -> str` — `-# ↩︎ [name](url)`
- Produces: `jump_url(guild_id: int, channel_id: int, message_id: int) -> str`
- Produces: `split_text(text: str, limit: int = 2000) -> list[str]` — 줄바꿈 우선 분할, 빈 조각 없음

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_formatting.py`

```python
from bot.formatting import build_reply_line, jump_url, split_text


def test_reply_line():
    assert (
        build_reply_line("몽실", "https://discord.com/channels/1/2/3")
        == "-# ↩︎ [몽실](https://discord.com/channels/1/2/3)"
    )


def test_jump_url():
    assert jump_url(1, 2, 3) == "https://discord.com/channels/1/2/3"


def test_split_short_text_single_chunk():
    assert split_text("짧다") == ["짧다"]


def test_split_prefers_newline():
    text = "a" * 1500 + "\n" + "b" * 1000
    parts = split_text(text)
    assert parts == ["a" * 1500, "b" * 1000]


def test_split_hard_cut_without_newline():
    text = "a" * 4500
    parts = split_text(text)
    assert [len(p) for p in parts] == [2000, 2000, 500]


def test_split_no_empty_chunks():
    parts = split_text("x" * 2000 + "\n")
    assert parts == ["x" * 2000]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_formatting.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현** — `bot/formatting.py`

```python
def build_reply_line(name: str, url: str) -> str:
    return f"-# ↩︎ [{name}]({url})"


def jump_url(guild_id: int, channel_id: int, message_id: int) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


def split_text(text: str, limit: int = 2000) -> list[str]:
    parts: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        parts.append(text)
    return parts
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_formatting.py -v`
Expected: PASS (6개)

- [ ] **Step 5: 커밋**

```bash
git add bot/formatting.py tests/test_formatting.py
git commit -m "feat: 인용줄·점프링크·메시지 분할 유틸 추가"
```

---

### Task 4: DeepL 클라이언트 (bot/translator.py)

**Files:**
- Create: `bot/translator.py`
- Test: `tests/test_translator.py`

**Interfaces:**
- Produces: `class QuotaExceeded(Exception)`, `class TranslationError(Exception)`
- Produces: `class DeepLClient: __init__(self, api_key: str, client: httpx.AsyncClient | None = None)`
- Produces: `async DeepLClient.translate(text: str, source: str, target: str) -> str`
  - `tag_handling="xml"`, `ignore_tags=["x"]` 포함해 호출
  - 456 → `QuotaExceeded`, 429/5xx/네트워크 오류 → 백오프 3회 재시도 후 `TranslationError`
  - Free 키(`:fx`) → `api-free.deepl.com`, 아니면 `api.deepl.com`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_translator.py`

```python
import httpx
import pytest

from bot.translator import DeepLClient, QuotaExceeded, TranslationError


def make_client(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return DeepLClient("test-key:fx", client=http)


@pytest.mark.asyncio
async def test_translate_success():
    captured = {}

    def handler(request):
        import json

        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"translations": [{"text": "こんにちは"}]}
        )

    client = make_client(handler)
    result = await client.translate("안녕하세요", "KO", "JA")
    assert result == "こんにちは"
    assert "api-free.deepl.com" in captured["url"]
    assert captured["body"]["tag_handling"] == "xml"
    assert captured["body"]["ignore_tags"] == ["x"]
    assert captured["body"]["source_lang"] == "KO"
    assert captured["body"]["target_lang"] == "JA"


@pytest.mark.asyncio
async def test_quota_exceeded_raises_immediately():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(456)

    client = make_client(handler)
    with pytest.raises(QuotaExceeded):
        await client.translate("안녕", "KO", "JA")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retry_then_success():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"translations": [{"text": "ok"}]})

    client = make_client(handler)
    client.RETRY_BASE_DELAY = 0
    assert await client.translate("안녕", "KO", "JA") == "ok"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_retries_exhausted():
    def handler(request):
        return httpx.Response(500)

    client = make_client(handler)
    client.RETRY_BASE_DELAY = 0
    with pytest.raises(TranslationError):
        await client.translate("안녕", "KO", "JA")


@pytest.mark.asyncio
async def test_paid_key_uses_main_host():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"translations": [{"text": "x"}]})

    transport = httpx.MockTransport(handler)
    client = DeepLClient("paid-key", client=httpx.AsyncClient(transport=transport))
    await client.translate("안녕", "KO", "JA")
    assert "//api.deepl.com" in captured["url"]
```

`pytest-asyncio` 설정 — `pyproject.toml` 생성:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

(`asyncio_mode = "auto"`이므로 `@pytest.mark.asyncio` 데코레이터는 없어도 동작하지만 명시해도 무해.)

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_translator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현** — `bot/translator.py`

```python
import asyncio

import httpx


class QuotaExceeded(Exception):
    pass


class TranslationError(Exception):
    pass


class DeepLClient:
    MAX_ATTEMPTS = 3
    RETRY_BASE_DELAY = 1.0

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        host = "api-free.deepl.com" if api_key.endswith(":fx") else "api.deepl.com"
        self._url = f"https://{host}/v2/translate"
        self._headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}
        self._client = client or httpx.AsyncClient(timeout=15)

    async def translate(self, text: str, source: str, target: str) -> str:
        body = {
            "text": [text],
            "source_lang": source,
            "target_lang": target,
            "tag_handling": "xml",
            "ignore_tags": ["x"],
        }
        last_error: Exception | None = None
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                resp = await self._client.post(
                    self._url, json=body, headers=self._headers
                )
            except httpx.HTTPError as e:
                last_error = e
                await asyncio.sleep(self.RETRY_BASE_DELAY * 2**attempt)
                continue
            if resp.status_code == 456:
                raise QuotaExceeded("DeepL 월 한도 초과")
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = TranslationError(f"HTTP {resp.status_code}")
                await asyncio.sleep(self.RETRY_BASE_DELAY * 2**attempt)
                continue
            resp.raise_for_status()
            return resp.json()["translations"][0]["text"]
        raise TranslationError(f"재시도 소진: {last_error}")

    async def close(self):
        await self._client.aclose()
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_translator.py -v`
Expected: PASS (5개)

- [ ] **Step 5: 커밋**

```bash
git add bot/translator.py tests/test_translator.py pyproject.toml
git commit -m "feat: DeepL 번역 클라이언트 추가"
```

---

### Task 5: 메시지 매핑 저장소 (bot/mapping.py)

**Files:**
- Create: `bot/mapping.py`
- Test: `tests/test_mapping.py`

**Interfaces:**
- Produces: `@dataclass MapRow: orig_id: int, trans_id: int, channel_id: int, author_id: int, direction: str` — direction은 `"KO>JA"` 또는 `"JA>KO"`
- Produces: `class MessageMap`
  - `async open(path: str)` — 연결 + 테이블 생성 (`:memory:` 허용)
  - `async add(row: MapRow)`
  - `async lookup(message_id: int) -> MapRow | None` — orig_id 또는 trans_id 어느 쪽으로든 조회
  - `async delete(orig_id: int)`
  - `async close()`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_mapping.py`

```python
import pytest

from bot.mapping import MapRow, MessageMap


@pytest.fixture
async def store():
    m = MessageMap()
    await m.open(":memory:")
    yield m
    await m.close()


ROW = MapRow(orig_id=100, trans_id=200, channel_id=1, author_id=42, direction="KO>JA")


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
async def test_delete(store):
    await store.add(ROW)
    await store.delete(100)
    assert await store.lookup(100) is None
    assert await store.lookup(200) is None
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현** — `bot/mapping.py`

```python
from dataclasses import dataclass

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS message_map (
    orig_id INTEGER PRIMARY KEY,
    trans_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
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


class MessageMap:
    _db: aiosqlite.Connection

    async def open(self, path: str):
        self._db = await aiosqlite.connect(path)
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def add(self, row: MapRow):
        await self._db.execute(
            "INSERT OR REPLACE INTO message_map"
            " (orig_id, trans_id, channel_id, author_id, direction)"
            " VALUES (?, ?, ?, ?, ?)",
            (row.orig_id, row.trans_id, row.channel_id, row.author_id, row.direction),
        )
        await self._db.commit()

    async def lookup(self, message_id: int) -> MapRow | None:
        cur = await self._db.execute(
            "SELECT orig_id, trans_id, channel_id, author_id, direction"
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
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_mapping.py -v`
Expected: PASS (4개)

- [ ] **Step 5: 커밋**

```bash
git add bot/mapping.py tests/test_mapping.py
git commit -m "feat: 원본-번역 메시지 매핑 저장소 추가"
```

---

### Task 6: 봇 본체 + 엔트리 (bot/client.py, main.py)

**Files:**
- Create: `bot/client.py`, `main.py`

**Interfaces:**
- Consumes: `detect_direction`, `mask`, `unmask`, `build_reply_line`, `jump_url`, `split_text`, `DeepLClient`, `QuotaExceeded`, `TranslationError`, `MessageMap`, `MapRow`
- Produces: `class StellaBot(discord.Client): __init__(self, *, channel_id: int, translator: DeepLClient, mapping: MessageMap, allow_bots: bool = False)`

동작 규칙 (스펙 그대로):

- 필터: 대상 채널 아님 / 자기 웹훅 메시지(`message.webhook_id == 자기 웹훅 id`) / `author.bot`이고 `allow_bots=False` / 빈 텍스트 → 무시. `allow_bots=True`는 E2E 스모크용 — 이때도 자기 웹훅 메시지는 항상 제외해 루프 방지
- 웹훅: 채널에서 자기가 만든 `stella-bot` 웹훅 찾기, 없으면 생성, 캐시
- 리플라이: `message.reference`가 있으면 매핑 조회. row가 있으면 번역 출력 언어와 같은 쪽 메시지로 점프링크 (`direction`이 `"KO>JA"`이고 출력이 JA면 trans_id, KO면 orig_id). row가 없으면 참조 메시지 자체를 링크. 이름은 `reference.resolved.author.display_name`, 없으면 `fetch_message`, 그래도 실패 시 `"원문"`
- 게시: `webhook.send(part, username=display_name, avatar_url=..., wait=True, allowed_mentions=none)`. 분할 시 첫 조각 id만 매핑에 저장
- 수정: `on_raw_message_edit` — 매핑에서 orig 쪽이면 원본 fetch → 재번역 → `webhook.edit_message(trans_id, ...)`. NotFound 무시
- 삭제: `on_raw_message_delete` — orig 쪽이면 번역문 삭제 + row 삭제, trans 쪽이면 row만 삭제
- 오류: `QuotaExceeded`/`TranslationError` → 원본에 ⚠️ 리액션 + `sentry_sdk.capture_exception`

- [ ] **Step 1: 구현** — `bot/client.py`

```python
import logging

import discord
import sentry_sdk

from bot.detect import detect_direction
from bot.formatting import build_reply_line, jump_url, split_text
from bot.mapping import MapRow, MessageMap
from bot.masking import mask, unmask
from bot.translator import DeepLClient, QuotaExceeded, TranslationError

log = logging.getLogger("stella")
WEBHOOK_NAME = "stella-bot"
NO_MENTIONS = discord.AllowedMentions.none()


class StellaBot(discord.Client):
    def __init__(
        self,
        *,
        channel_id: int,
        translator: DeepLClient,
        mapping: MessageMap,
        allow_bots: bool = False,
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.channel_id = channel_id
        self.translator = translator
        self.mapping = mapping
        self.allow_bots = allow_bots
        self._webhook: discord.Webhook | None = None

    async def on_ready(self):
        log.info("로그인: %s", self.user)

    async def _get_webhook(self) -> discord.Webhook:
        if self._webhook is None:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(
                self.channel_id
            )
            for wh in await channel.webhooks():
                if wh.name == WEBHOOK_NAME and wh.user == self.user:
                    self._webhook = wh
                    break
            else:
                self._webhook = await channel.create_webhook(name=WEBHOOK_NAME)
        return self._webhook

    def _should_skip(self, message: discord.Message) -> bool:
        if message.channel.id != self.channel_id:
            return True
        if self._webhook and message.webhook_id == self._webhook.id:
            return True
        if message.author.bot and not self.allow_bots:
            return True
        if not message.content.strip():
            return True
        return False

    async def _translate_content(self, content: str) -> tuple[str, str] | None:
        """번역문과 방향 문자열을 반환. 번역 대상이 아니면 None."""
        direction = detect_direction(content)
        if direction is None:
            return None
        source, target = direction
        masked, spans = mask(content)
        translated = await self.translator.translate(masked, source, target)
        return unmask(translated, spans), f"{source}>{target}"

    async def _reply_line(
        self, message: discord.Message, target: str
    ) -> str | None:
        ref = message.reference
        if ref is None or ref.message_id is None:
            return None
        row = await self.mapping.lookup(ref.message_id)
        if row is None:
            link_id = ref.message_id
        elif row.direction.endswith(target):
            link_id = row.trans_id
        else:
            link_id = row.orig_id
        url = jump_url(message.guild.id, self.channel_id, link_id)
        name = "원문"
        resolved = ref.resolved
        if isinstance(resolved, discord.Message):
            name = resolved.author.display_name
        else:
            try:
                fetched = await message.channel.fetch_message(ref.message_id)
                name = fetched.author.display_name
            except discord.HTTPException:
                pass
        return build_reply_line(name, url)

    async def on_message(self, message: discord.Message):
        # 자기 웹훅 판별 전에 웹훅 캐시가 없으면 채워둔다
        if self._webhook is None and message.channel.id == self.channel_id:
            await self._get_webhook()
        if self._should_skip(message):
            return
        try:
            result = await self._translate_content(message.content)
            if result is None:
                return
            translated, direction = result
            line = await self._reply_line(message, direction[-2:])
            if line:
                translated = f"{line}\n{translated}"
            webhook = await self._get_webhook()
            first_id: int | None = None
            for part in split_text(translated):
                sent = await webhook.send(
                    part,
                    username=message.author.display_name,
                    avatar_url=message.author.display_avatar.url,
                    wait=True,
                    allowed_mentions=NO_MENTIONS,
                )
                if first_id is None:
                    first_id = sent.id
            await self.mapping.add(
                MapRow(
                    orig_id=message.id,
                    trans_id=first_id,
                    channel_id=self.channel_id,
                    author_id=message.author.id,
                    direction=direction,
                )
            )
        except (QuotaExceeded, TranslationError) as e:
            sentry_sdk.capture_exception(e)
            try:
                await message.add_reaction("⚠️")
            except discord.HTTPException:
                pass

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if payload.channel_id != self.channel_id:
            return
        row = await self.mapping.lookup(payload.message_id)
        if row is None or row.orig_id != payload.message_id:
            return
        try:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(
                self.channel_id
            )
            message = await channel.fetch_message(payload.message_id)
            result = await self._translate_content(message.content)
            if result is None:
                return
            translated, direction = result
            line = await self._reply_line(message, direction[-2:])
            if line:
                translated = f"{line}\n{translated}"
            webhook = await self._get_webhook()
            await webhook.edit_message(
                row.trans_id,
                content=split_text(translated)[0],
                allowed_mentions=NO_MENTIONS,
            )
        except discord.NotFound:
            pass
        except (QuotaExceeded, TranslationError) as e:
            sentry_sdk.capture_exception(e)

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.channel_id != self.channel_id:
            return
        row = await self.mapping.lookup(payload.message_id)
        if row is None:
            return
        if row.orig_id == payload.message_id:
            try:
                webhook = await self._get_webhook()
                await webhook.delete_message(row.trans_id)
            except discord.NotFound:
                pass
        await self.mapping.delete(row.orig_id)
```

- [ ] **Step 2: 구현** — `main.py`

```python
import asyncio
import logging
import os

import sentry_sdk
from dotenv import load_dotenv

from bot.client import StellaBot
from bot.mapping import MessageMap
from bot.translator import DeepLClient


async def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    dsn = os.getenv("SENTRY_DSN")
    if dsn:
        sentry_sdk.init(dsn=dsn)

    mapping = MessageMap()
    os.makedirs("data", exist_ok=True)
    await mapping.open("data/stella.db")
    translator = DeepLClient(os.environ["DEEPL_API_KEY"])

    bot = StellaBot(
        channel_id=int(os.environ["CHANNEL_ID"]),
        translator=translator,
        mapping=mapping,
        allow_bots=os.getenv("ALLOW_BOT_MESSAGES") == "1",
    )
    try:
        await bot.start(os.environ["DISCORD_TOKEN"])
    finally:
        await translator.close()
        await mapping.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: 전체 테스트 + import 확인**

Run: `python -m pytest -v && python -c "import main"`
Expected: 기존 테스트 전부 PASS, import 오류 없음

- [ ] **Step 4: 커밋**

```bash
git add bot/client.py main.py
git commit -m "feat: 번역 파이프라인·웹훅 게시·동기화 이벤트 연결"
```

---

### Task 7: 라이브 스모크 테스트 (실제 Discord + DeepL)

**Files:**
- Create: `.env` (커밋 금지 — .gitignore에 이미 있음)
- Create: 스크래치패드에 검증 스크립트 (레포 밖)

**Interfaces:**
- Consumes: 실행 중인 봇 프로세스, 테스트 채널, REST API

준비: `.env`에 사용자 제공 `DISCORD_TOKEN`, `DEEPL_API_KEY`, `CHANNEL_ID=1531986683631763476`, `ALLOW_BOT_MESSAGES=1` 기입. venv 만들고 `pip install -r requirements.txt`.

검증 방법: 봇 토큰으로 REST 호출해 테스트 메시지를 만들고(`POST /channels/{id}/messages` — author가 봇 자신이지만 `ALLOW_BOT_MESSAGES=1`이라 번역됨), 채널 메시지를 `GET /channels/{id}/messages`로 읽어 웹훅 번역문을 확인한다.

- [ ] **Step 1: 봇 백그라운드 실행, 로그인 로그 확인**
- [ ] **Step 2: KO→JA** — "안녕하세요! 오늘 스크림 몇 시에 해요?" 게시 → 웹훅 번역문(일본어, username 일치) 확인
- [ ] **Step 3: JA→KO** — "今日は21時からで大丈夫ですか？" 게시 → 한국어 번역문 확인
- [ ] **Step 4: 리플라이** — Step 2 번역문 메시지에 `message_reference`로 일본어 답장 게시 → 번역문에 `-# ↩︎` 인용줄 + 한국어 원문 점프링크 확인
- [ ] **Step 5: 이모지/코드 보존** — 커스텀 이모지·인라인코드 섞인 메시지 → 번역문에 원형 보존 확인
- [ ] **Step 6: 수정 동기화** — Step 2 원본 PATCH → 번역문 edit 확인
- [ ] **Step 7: 삭제 동기화** — Step 3 원본 DELETE → 번역문 삭제 확인
- [ ] **Step 8: 영어 스킵** — "gg wp" 게시 → 번역문 없음 확인
- [ ] **Step 9: `.env`에서 `ALLOW_BOT_MESSAGES` 제거, 봇 재시작 → 봇 메시지 무시 확인**
- [ ] **Step 10: 발견된 버그는 systematic-debugging으로 수정 후 커밋**

---

### Task 8: GitHub private 레포 생성 + push

- [ ] **Step 1:** `gh repo create MongsilDev/stella-bot --private --source . --push`
- [ ] **Step 2:** `git log --oneline`으로 커밋 분리 상태 확인, 원격 push 확인

---

## Self-Review 결과

- 스펙 커버리지: 언어 감지(T1), 마스킹(T2), 인용줄·분할(T3), DeepL·재시도·456(T4), 매핑(T5), 웹훅 게시·리플라이·수정·삭제·⚠️·allowed_mentions(T6), E2E(T7), GitHub private(T8) — 전부 매핑됨. NAS PMC 배포는 사용자가 "테스트까지"로 한정해 계획 범위 외.
- 플레이스홀더: 없음
- 타입 일관성: `detect_direction` 반환 tuple → `_translate_content`의 `f"{source}>{target}"` → `MapRow.direction` `"KO>JA"` 형식 → `_reply_line`의 `direction.endswith(target)` 일치 확인
