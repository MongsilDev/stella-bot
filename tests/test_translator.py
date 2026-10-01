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
async def test_no_sleep_after_last_attempt(monkeypatch):
    delays = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr("bot.translator.asyncio.sleep", fake_sleep)
    client = make_client(lambda request: httpx.Response(500))
    with pytest.raises(TranslationError):
        await client.translate("안녕", "KO", "JA")
    assert delays == [1.0, 2.0]


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


@pytest.mark.asyncio
async def test_warmup_hits_usage_endpoint():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"character_count": 0})

    client = make_client(handler)
    await client.warmup()
    assert captured["url"].endswith("/v2/usage")


@pytest.mark.asyncio
async def test_warmup_swallows_errors():
    def handler(request):
        raise httpx.ConnectError("down")

    client = make_client(handler)
    await client.warmup()


@pytest.mark.asyncio
async def test_next_gen_model_requested():
    captured = {}

    def handler(request):
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"translations": [{"text": "x"}]})

    client = make_client(handler)
    await client.translate("안녕", "KO", "JA")
    assert captured["body"]["model_type"] == "prefer_quality_optimized"
    assert "context" not in captured["body"]


@pytest.mark.asyncio
async def test_context_passed_through():
    captured = {}

    def handler(request):
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"translations": [{"text": "x"}]})

    client = make_client(handler)
    await client.translate("안녕", "KO", "JA", context="몽실: 이전 대화")
    assert captured["body"]["context"] == "몽실: 이전 대화"


@pytest.mark.asyncio
async def test_glossary_included_when_set():
    captured = {}

    def handler(request):
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"translations": [{"text": "x"}]})

    transport = httpx.MockTransport(handler)
    client = DeepLClient(
        "test-key:fx",
        client=httpx.AsyncClient(transport=transport),
        glossary_id="gid-123",
    )
    await client.translate("안녕", "KO", "JA")
    assert captured["body"]["glossary_id"] == "gid-123"


@pytest.mark.asyncio
async def test_glossary_absent_by_default():
    captured = {}

    def handler(request):
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"translations": [{"text": "x"}]})

    client = make_client(handler)
    await client.translate("안녕", "KO", "JA")
    assert "glossary_id" not in captured["body"]


@pytest.mark.asyncio
async def test_bad_request_raises_translation_error_without_retry():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={"message": "Tag handling parsing failed"})

    client = make_client(handler)
    with pytest.raises(TranslationError):
        await client.translate("안녕", "KO", "JA")
    assert len(calls) == 1
