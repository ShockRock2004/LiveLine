import asyncio
import json
import threading
from dataclasses import dataclass

import httpx
import numpy as np
from faster_whisper import WhisperModel
from piper import PiperVoice

from liveline.audio import SileroVad, resample


class SpeechToText:
    def __init__(self):
        self.models: dict[str, WhisperModel] = {}
        self.lock = threading.Lock()   # one GPU, one transcription at a time

    def transcribe(self, audio_16k: np.ndarray, model: str, beam_size: int) -> str:
        with self.lock:
            if model not in self.models:
                self.models[model] = WhisperModel(model, device="cuda", compute_type="int8_float16")
            segments, _ = self.models[model].transcribe(
                audio_16k, language="en", beam_size=beam_size,
                condition_on_previous_text=False, without_timestamps=True)
            return " ".join(s.text.strip() for s in segments).strip()


class TextToSpeech:
    def __init__(self):
        self.voices: dict[str, PiperVoice] = {}
        self.lock = threading.Lock()

    def synthesize(self, text: str, voice_path: str) -> np.ndarray:
        """Returns int16 samples at 8 kHz."""
        with self.lock:
            if voice_path not in self.voices:
                self.voices[voice_path] = PiperVoice.load(voice_path)
            chunks = list(self.voices[voice_path].synthesize(text))
        if not chunks:
            return np.zeros(0, np.int16)
        pcm = np.concatenate([np.frombuffer(c.audio_int16_bytes, np.int16) for c in chunks])
        return resample(pcm, chunks[0].sample_rate, 8000)


class Ollama:
    def __init__(self, url: str):
        self.http = httpx.AsyncClient(base_url=url, timeout=60)

    async def prepare(self, model: str) -> None:
        """Pull the model if missing and keep it loaded on the GPU."""
        names = {m["name"] for m in (await self.http.get("/api/tags")).json()["models"]}
        if model not in names:
            await self.http.post("/api/pull", json={"model": model, "stream": False}, timeout=None)
        await self.http.post("/api/generate", json={"model": model, "keep_alive": -1})

    async def stream_chat(self, model: str, messages: list[dict], max_tokens: int):
        body = {"model": model, "messages": messages, "stream": True, "keep_alive": -1,
                "options": {"num_predict": max_tokens, "temperature": 0.3}}
        async with self.http.stream("POST", "/api/chat", json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line and (text := json.loads(line).get("message", {}).get("content")):
                    yield text


@dataclass
class Engines:
    vad: SileroVad
    stt: SpeechToText
    llm: Ollama
    tts: TextToSpeech


async def load_engines(s) -> Engines:
    engines = Engines(SileroVad(s.vad_model), SpeechToText(), Ollama(s.ollama_url), TextToSpeech())
    # Run every model once so the first caller does not pay the loading cost.
    await engines.llm.prepare(s.llm_model)
    await asyncio.to_thread(engines.stt.transcribe, np.zeros(16000, np.float32),
                            s.whisper_model, s.whisper_beam_size)
    await asyncio.to_thread(engines.tts.synthesize, "Ready.", s.piper_voice)
    return engines
