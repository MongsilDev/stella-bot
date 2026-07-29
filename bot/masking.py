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
