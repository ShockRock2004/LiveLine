from math import gcd

import numpy as np
import onnxruntime as ort
from scipy.signal import resample_poly

CHUNK = 256   # samples per VAD decision: 32 ms at 8 kHz
CHUNK_MS = 32


def _ulaw_tables():
    """G.711 mu-law: lookup tables for all 256 bytes and all 65536 samples."""
    decode = np.zeros(256, np.int16)
    for byte in range(256):
        u = ~byte & 0xFF
        magnitude = ((((u & 0x0F) << 3) + 0x84) << ((u >> 4) & 7)) - 0x84
        decode[byte] = -magnitude if u & 0x80 else magnitude
    x = np.arange(-32768, 32768)
    magnitude = np.minimum(np.abs(x), 32635) + 0x84
    exponent = np.floor(np.log2(magnitude)).astype(int) - 7
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    encode = ~(np.where(x < 0, 0x80, 0) | (exponent << 4) | mantissa) & 0xFF
    return decode, encode.astype(np.uint8)


DECODE, ENCODE = _ulaw_tables()


def ulaw_to_pcm(data: bytes) -> np.ndarray:
    return DECODE[np.frombuffer(data, np.uint8)]


def pcm_to_ulaw(pcm: np.ndarray) -> bytes:
    return ENCODE[pcm.astype(np.int32) + 32768].tobytes()


def to_float(pcm: np.ndarray) -> np.ndarray:
    return pcm.astype(np.float32) / 32768


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    g = gcd(src, dst)
    y = resample_poly(x.astype(np.float32), dst // g, src // g)
    if x.dtype == np.int16:
        return np.clip(np.round(y), -32768, 32767).astype(np.int16)
    return y.astype(np.float32)


class SileroVad:
    def __init__(self, model_path: str):
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(model_path, options, providers=["CPUExecutionProvider"])

    def stream(self) -> "VadStream":
        return VadStream(self.session)


class VadStream:
    """Per-call model state: the probability that each 32 ms chunk is speech."""

    def __init__(self, session):
        self.session = session
        self.state = np.zeros((2, 1, 128), np.float32)
        self.context = np.zeros(32, np.float32)

    def probability(self, chunk: np.ndarray) -> float:
        x = np.concatenate([self.context, chunk])[None]
        out, self.state = self.session.run(
            None, {"input": x, "state": self.state, "sr": np.array(8000, np.int64)})
        self.context = chunk[-32:]
        return float(out[0][0])


class TurnDetector:
    """Turns per-chunk speech yes/no into "start", "end" (a sentence) or "discard" (a cough)."""

    def __init__(self, settings):
        self.s = settings
        self.in_speech = False
        self.speech_run = self.silence_run = self.speech_total = 0

    def push(self, is_speech: bool) -> str | None:
        if is_speech:
            self.speech_run, self.silence_run = self.speech_run + 1, 0
        else:
            self.speech_run, self.silence_run = 0, self.silence_run + 1

        if not self.in_speech:
            if self.speech_run * CHUNK_MS >= self.s.speech_start_ms:
                self.in_speech, self.speech_total = True, self.speech_run
                return "start"
            return None
        if is_speech:
            self.speech_total += 1
            return None
        if self.silence_run * CHUNK_MS < self.s.end_of_turn_ms:
            return None
        self.in_speech = False
        return "end" if self.speech_total * CHUNK_MS >= self.s.min_speech_ms else "discard"
