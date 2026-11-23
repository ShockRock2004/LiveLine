"""Whole calls with fake models: no GPU, Ollama or model files needed."""
import asyncio
import base64
import json

import numpy as np

from liveline.audio import pcm_to_ulaw
from liveline.engines import Engines
from liveline.metrics import CallLog
from liveline.session import CallSession
from liveline.settings import Settings
from liveline.telephony import Twilio


class LoudVad:
    def stream(self):
        return self

    def probability(self, chunk):
        return float(np.sqrt(np.mean(chunk ** 2)) > 0.1)


class FakeStt:
    def transcribe(self, audio, model, beam_size):
        return "I want to book a cleaning"


class FakeLlm:
    async def stream_chat(self, model, messages, max_tokens):
        for piece in ["Sure", ", I can help. ", "What is your", " name?"]:
            await asyncio.sleep(0.01)
            yield piece


class FakeTts:
    def synthesize(self, text, voice):
        return np.zeros(800, np.int16)


def frames(seconds: float, loud: bool) -> list[str]:
    n = int(seconds * 8000)
    pcm = (np.sin(np.arange(n) * 0.3) * 16000).astype(np.int16) if loud else np.zeros(n, np.int16)
    ulaw = pcm_to_ulaw(pcm)
    return [json.dumps({"event": "media", "media": {"payload": base64.b64encode(ulaw[i:i + 160]).decode()}})
            for i in range(0, len(ulaw), 160)]


async def start_call():
    sent = []

    async def send(text):
        sent.append(json.loads(text))

    log = CallLog()
    session = CallSession(send, Twilio(), Engines(LoudVad(), FakeStt(), FakeLlm(), FakeTts()), Settings(), log)
    await session.handle(json.dumps({"event": "start", "start": {"streamSid": "MZ1", "callSid": "CA1"}}))
    await session.reply
    return session, sent, log


async def feed(session, messages):
    for message in messages:
        await session.handle(message)


async def played(session, mark):
    await session.handle(json.dumps({"event": "mark", "mark": {"name": mark["mark"]["name"]}}))


async def test_greeting_then_two_sentence_reply():
    session, sent, log = await start_call()
    assert [m["event"] for m in sent] == ["media", "mark"]
    await played(session, sent[1])
    await feed(session, frames(1.0, True) + frames(0.7, False))
    await session.reply
    assert [m["event"] for m in sent[2:]] == ["media", "mark", "media", "mark"]
    turn = log.recent()[0]["turns"][0]
    assert turn["user_text"] == "I want to book a cleaning"
    assert turn["reply_text"] == "Sure, I can help. What is your name?"
    assert turn["total_ms"] >= turn["llm_ms"] > 0


async def test_barge_in_clears_audio():
    session, sent, log = await start_call()
    await feed(session, frames(0.2, True))
    assert sent[-1] == {"event": "clear", "streamSid": "MZ1"}
    assert len(log.recent()[0]["barge_in_ms"]) == 1


async def test_history_keeps_only_heard_sentences():
    session, sent, log = await start_call()
    await played(session, sent[1])
    await feed(session, frames(1.0, True) + frames(0.7, False))
    await session.reply
    await played(session, sent[3])          # first sentence played, then the caller interrupts
    await feed(session, frames(0.2, True))
    assert session.history[-1]["content"] == "Sure, I can help."
