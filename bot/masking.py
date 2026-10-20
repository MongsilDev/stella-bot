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
EMOJI = re.compile(r"<a?:(\w+):\d+>")
MENTION = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _unescape(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def mask(text: str) -> tuple[str, list[str]]:
    """보존 구간을 토큰으로 치환하고 나머지는 XML 이스케이프한다.

    DeepL을 tag_handling=xml로 호출하므로 본문의 홑 <, >, &가 그대로 전달되면
    파싱 실패(400)가 난다.
    """
    spans: list[str] = []
    out: list[str] = []
    last = 0
    for m in PRESERVE.finditer(text):
        out.append(_escape(text[last : m.start()]))
        spans.append(m.group(0))
        out.append(f'<x i="{len(spans) - 1}"/>')
        last = m.end()
    out.append(_escape(text[last:]))
    return "".join(out), spans


def unmask(text: str, spans: list[str]) -> str:
    text = _unescape(text)

    def repl(m: re.Match) -> str:
        i = int(m.group(1))
        return spans[i] if i < len(spans) else m.group(0)

    return TOKEN.sub(repl, text)


def strip_discord_tokens(text: str) -> str:
    """번역 문맥(context)용 정제. 이모지는 이름만 남기고 XML 특수문자를 없앤다."""
    text = EMOJI.sub(r":\1:", text)
    text = MENTION.sub("", text)
    return text.replace("<", "").replace(">", "").replace("&", " ")
