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
