import numpy as np

from liveline.audio import TurnDetector, pcm_to_ulaw, resample, ulaw_to_pcm
from liveline.settings import Settings


def test_ulaw_known_values_and_round_trip():
    assert pcm_to_ulaw(np.array([0, 32767, -32768], np.int16)) == b"\xff\x80\x00"
    assert ulaw_to_pcm(b"\x80")[0] == 32124
    every_byte = bytes(range(256))
    assert pcm_to_ulaw(ulaw_to_pcm(every_byte)) == every_byte.replace(b"\x7f", b"\xff")


def test_ulaw_error_is_about_3_percent():
    x = np.linspace(-30000, 30000, 2001).astype(np.int16)
    error = np.abs(ulaw_to_pcm(pcm_to_ulaw(x)).astype(int) - x)
    assert np.all(error <= np.maximum(16, np.abs(x) * 0.035))


def test_resample_keeps_pitch():
    tone = (np.sin(2 * np.pi * 440 * np.arange(8000) / 8000) * 10000).astype(np.int16)
    up = resample(tone, 8000, 16000)
    assert up.dtype == np.int16 and len(up) == 16000
    assert abs(np.argmax(np.abs(np.fft.rfft(up))) - 440) < 2


def events(pattern: str) -> list[str]:
    """S = 32 ms of speech, . = 32 ms of silence."""
    detector = TurnDetector(Settings(end_of_turn_ms=480))
    return [e for e in (detector.push(c == "S") for c in pattern) if e]


def test_turn_detection():
    assert events("S" * 20 + "." * 15) == ["start", "end"]
    assert events("S.S.S.S." + "." * 20) == []                                   # never 2 in a row
    assert events("S" * 10 + "." * 10 + "S" * 10 + "." * 15) == ["start", "end"]  # short pause
    assert events("SSS" + "." * 15) == ["start", "discard"]                       # a cough
