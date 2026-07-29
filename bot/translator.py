import asyncio

import httpx


class QuotaExceeded(Exception):
    pass


class TranslationError(Exception):
    pass


class DeepLClient:
    MAX_ATTEMPTS = 3
    RETRY_BASE_DELAY = 1.0

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        glossary_id: str | None = None,
    ):
        host = "api-free.deepl.com" if api_key.endswith(":fx") else "api.deepl.com"
        self._url = f"https://{host}/v2/translate"
        self._usage_url = f"https://{host}/v2/usage"
        self._headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}
        self._client = client or httpx.AsyncClient(timeout=15)
        self._glossary_id = glossary_id

    async def warmup(self):
        """TLS 연결을 미리 열어 첫 번역의 핸드셰이크 지연을 없앤다."""
        try:
            await self._client.get(self._usage_url, headers=self._headers)
        except httpx.HTTPError:
            pass

    async def translate(
        self, text: str, source: str, target: str, context: str | None = None
    ) -> str:
        body = {
            "text": [text],
            "source_lang": source,
            "target_lang": target,
            "tag_handling": "xml",
            "ignore_tags": ["x"],
            "model_type": "prefer_quality_optimized",
        }
        if context:
            body["context"] = context
        if self._glossary_id:
            body["glossary_id"] = self._glossary_id
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
