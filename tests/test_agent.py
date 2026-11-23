from liveline.agent import SentenceBuffer


def feed_all(pieces: list[str]) -> list[str]:
    buffer = SentenceBuffer()
    out = [s for piece in pieces for s in buffer.feed(piece)]
    return out + ([rest] if (rest := buffer.flush()) else [])


def test_sentences_cut_across_pieces():
    assert feed_all(["Sure", ", I can", " help. What is", " your name?"]) == \
        ["Sure, I can help.", "What is your name?"]


def test_first_sentence_is_released_early():
    buffer = SentenceBuffer()
    assert buffer.feed("We open at 9. ") == ["We open at 9."]
    assert buffer.feed("We close at") == []


def test_decimals_abbreviations_and_markdown():
    assert feed_all(["It costs 1.5 thousand. Dr. Meera Nair will see you."]) == \
        ["It costs 1.5 thousand.", "Dr. Meera Nair will see you."]
    assert feed_all(["**Yes**, we are open. "]) == ["Yes, we are open."]
