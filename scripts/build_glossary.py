"""이터널 리턴 공식 l10n과 팀 용어로 DeepL 용어집을 만든다.

사용법: python scripts/build_glossary.py
필요 env: DEEPL_API_KEY, ER_API_KEY (.env에서 로드)
결과: DeepL 계정에 v3 용어집 stella 생성(ko>ja, ja>ko 사전 2개, 기존 것 교체),
      config/glossary_ids.json에 id 기록

Free 플랜은 용어집을 1개만 허용하므로 v3의 다중 사전으로 양방향을 담는다.
"""
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# 우선순위 순서. 같은 원문이 여러 카테고리에 있으면 앞선 카테고리가 이긴다.
CATEGORIES = [
    "Character/Name/",
    "Monster/Name/",
    "Area/Name/",
    "WeaponType/",
    "Trait/Name/",
    "Item/Name/",
    "Skin/Name/",
    "Collection/Name/",
]
# 일상어와 충돌하는 항목 제외
STOPWORDS = {"무작위", "없음", "전체", "일반", "기본"}


def fetch_l10n(lang: str, api_key: str) -> dict[str, str]:
    meta = httpx.get(
        f"https://open-api.bser.io/v1/l10n/{lang}",
        headers={"x-api-key": api_key},
        timeout=30,
    )
    meta.raise_for_status()
    text = httpx.get(meta.json()["data"]["l10Path"], timeout=60).text
    entries = {}
    for line in text.splitlines():
        if "┃" in line:
            key, _, value = line.partition("┃")
            entries[key] = value.strip()
    return entries


def collect_pairs(ko: dict[str, str], ja: dict[str, str]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for prefix in CATEGORIES:
        for key, src in ko.items():
            if not key.startswith(prefix):
                continue
            dst = ja.get(key, "").strip()
            if (
                len(src) < 2
                or not dst
                or src in STOPWORDS
                or src == dst
                or src.isascii()
                or "\t" in src + dst
                or "\n" in src + dst
            ):
                continue
            pairs.setdefault(src, dst)
    return pairs


def load_team_terms(path: Path) -> dict[str, str]:
    pairs = {}
    for line in path.read_text().splitlines():
        if "\t" in line:
            src, _, dst = line.partition("\t")
            if src.strip() and dst.strip():
                pairs[src.strip()] = dst.strip()
    return pairs


def dictionary(source: str, target: str, pairs: dict[str, str]) -> dict:
    return {
        "source_lang": source,
        "target_lang": target,
        "entries": "\n".join(f"{s}\t{d}" for s, d in pairs.items()),
        "entries_format": "tsv",
    }


def replace_glossary(
    client: httpx.Client, headers: dict, base: str,
    ko_ja: dict[str, str], ja_ko: dict[str, str],
) -> str:
    existing = client.get(f"{base}/v3/glossaries", headers=headers).json()["glossaries"]
    for g in existing:
        if g["name"] == "stella":
            client.delete(
                f"{base}/v3/glossaries/{g['glossary_id']}",
                headers=headers,
            )
    resp = client.post(
        f"{base}/v3/glossaries",
        headers=headers,
        json={
            "name": "stella",
            "dictionaries": [
                dictionary("ko", "ja", ko_ja),
                dictionary("ja", "ko", ja_ko),
            ],
        },
    )
    resp.raise_for_status()
    created = resp.json()
    for d in created["dictionaries"]:
        print(f"{d['source_lang']}>{d['target_lang']}: {d['entry_count']}개 항목")
    return created["glossary_id"]


def main():
    load_dotenv(ROOT / ".env")
    deepl_key = os.environ["DEEPL_API_KEY"]
    er_key = os.environ.get("ER_API_KEY")
    if not er_key:
        sys.exit("ER_API_KEY가 .env에 필요합니다")

    ko = fetch_l10n("Korean", er_key)
    ja = fetch_l10n("Japanese", er_key)
    print(f"l10n 로드: 한국어 {len(ko)}개, 일본어 {len(ja)}개 키")

    ko_ja = collect_pairs(ko, ja)
    ja_ko = {d: s for s, d in ko_ja.items() if not d.isascii()}

    # 팀 용어가 l10n보다 우선한다
    ko_ja.update(load_team_terms(ROOT / "config" / "team_terms_ko_ja.tsv"))
    ja_ko.update(load_team_terms(ROOT / "config" / "team_terms_ja_ko.tsv"))

    host = "api-free.deepl.com" if deepl_key.endswith(":fx") else "api.deepl.com"
    headers = {"Authorization": f"DeepL-Auth-Key {deepl_key}"}
    with httpx.Client(timeout=60) as client:
        gid = replace_glossary(client, headers, f"https://{host}", ko_ja, ja_ko)

    out = ROOT / "config" / "glossary_ids.json"
    out.write_text(json.dumps({"glossary_id": gid}, indent=2) + "\n")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
