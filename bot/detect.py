import re

HANGUL = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")
KANA = re.compile(r"[぀-ゟ゠-ヿ]")
HAN = re.compile(r"[一-鿿]")


def detect_direction(text: str) -> tuple[str, str] | None:
    """한글과 가나 문자 수로 원문 언어를 판정한다. 한자만 있으면 일본어로 간주."""
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
