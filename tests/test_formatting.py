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
