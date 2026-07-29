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


def test_raw_angle_brackets_escaped_for_xml():
    masked, spans = mask("3<5 인건 맞음")
    assert masked == "3&lt;5 인건 맞음"
    assert unmask(masked, spans) == "3<5 인건 맞음"


def test_ampersand_escaped_for_xml():
    masked, _ = mask("A&B 조합")
    assert masked == "A&amp;B 조합"


def test_escape_and_emoji_roundtrip():
    src = "3<5 <:wave:1234567890> A&B"
    masked, spans = mask(src)
    assert "<:wave:" not in masked
    assert "3&lt;5" in masked
    assert unmask(masked, spans) == src


def test_strip_discord_tokens_for_context():
    from bot.masking import strip_discord_tokens

    out = strip_discord_tokens("하레: <:jan:1049916547872870410> <@45> 3<5 봐")
    assert "<" not in out and ">" not in out
    assert ":jan:" in out
    assert "하레" in out
