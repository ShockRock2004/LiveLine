"""One phone call: listen with VAD, reply sentence by sentence, stop at once on barge-in."""
import asyncio
import itertools
import logging
from collections import deque

import numpy as np

from liveline.agent import GREETING, SentenceBuffer, build_messages
from liveline.audio import CHUNK, TurnDetector, pcm_to_ulaw, resample, to_float, ulaw_to_pcm
from liveline.metrics import Turn, now_ms

log = logging.getLogger("liveline")


class CallSession:
    def __init__(self, send, phone, engines, settings, call_log):
        self.send, self.phone, self.engines, self.s, self.log = send, phone, engines, settings, call_log
        self.call = None
        self.vad = engines.vad.stream()
        self.turns = TurnDetector(settings)
        self.pending = np.zeros(0, np.int16)
        self.preroll = deque(maxlen=10)    # 320 ms from before speech was detected
        self.utterance, self.carry, self.last_chunks = [], [], []
        self.was_speech = False
        self.speech_started_at = self.last_speech_at = 0.0

        self.history: list[dict] = []
        self.reply: asyncio.Task | None = None
        self.spoke = False                 # has the current reply sent audio yet?
        self.turn: Turn | None = None
        self.marks: dict[str, tuple[dict, str]] = {}   # mark -> (history message, sentence)
        self.mark_ids = itertools.count()

    @property
    def speaking(self) -> bool:
        return bool(self.marks) or (self.reply is not None and not self.reply.done())

    async def handle(self, raw: str) -> None:
        msg = self.phone.parse(raw)
        if msg.kind == "start":
            self.call = self.log.start(msg.call_id, self.phone.name)
            self.start_reply(self.greet())
        elif msg.kind == "audio":
            await self.on_audio(msg.audio)
        elif msg.kind == "played":
            self.on_played(msg.mark)
        elif msg.kind == "stop":
            self.close()

    def close(self) -> None:
        if self.reply:
            self.reply.cancel()

    # ---- listening

    async def on_audio(self, ulaw: bytes) -> None:
        self.pending = np.concatenate([self.pending, ulaw_to_pcm(ulaw)])
        while len(self.pending) >= CHUNK:
            chunk, self.pending = self.pending[:CHUNK], self.pending[CHUNK:]
            await self.on_chunk(chunk)

    async def on_chunk(self, chunk: np.ndarray) -> None:
        now = now_ms()
        is_speech = self.vad.probability(to_float(chunk)) >= self.s.vad_threshold
        if is_speech:
            if not self.was_speech:
                self.speech_started_at = now
            self.last_speech_at = now
        self.was_speech = is_speech
        (self.utterance if self.turns.in_speech else self.preroll).append(chunk)

        event = self.turns.push(is_speech)
        if event == "start":
            self.utterance = list(self.preroll)
            self.preroll.clear()
            if self.speaking:
                await self.barge_in()
        elif event == "end":
            chunks, self.carry, self.utterance = self.carry + self.utterance, [], []
            self.start_reply(self.answer(chunks, self.last_speech_at))
        elif event == "discard":
            self.utterance = []

    def on_played(self, name: str) -> None:
        """The caller heard this sentence, so it joins the conversation history."""
        if name in self.marks:
            message, sentence = self.marks.pop(name)
            message["content"] = f"{message['content']} {sentence}".strip()

    async def barge_in(self) -> None:
        self.reply.cancel()
        if self.spoke or self.marks:
            await self.send(self.phone.clear())
            self.marks.clear()
            self.call.barge_in_ms.append(now_ms() - self.speech_started_at)
            if self.turn:
                self.turn.interrupted = True
        else:
            self.carry = self.last_chunks    # caller only paused: join both halves

    # ---- speaking

    def start_reply(self, coroutine) -> None:
        self.spoke, self.turn = False, None
        self.reply = asyncio.create_task(coroutine)
        self.reply.add_done_callback(
            lambda t: t.cancelled() or not t.exception() or log.error("reply failed", exc_info=t.exception()))

    async def greet(self) -> None:
        pcm = await asyncio.to_thread(self.engines.tts.synthesize, GREETING, self.s.piper_voice)
        message = {"role": "assistant", "content": ""}
        self.history.append(message)
        await self.speak(pcm, GREETING, message)

    async def answer(self, chunks: list[np.ndarray], speech_end: float) -> None:
        self.last_chunks = chunks
        turn = Turn(endpoint_ms=now_ms() - speech_end)
        start = now_ms()
        audio = resample(to_float(np.concatenate(chunks)), 8000, 16000)
        turn.user_text = await asyncio.to_thread(
            self.engines.stt.transcribe, audio, self.s.whisper_model, self.s.whisper_beam_size)
        turn.stt_ms = now_ms() - start
        if not turn.user_text:
            return

        user = {"role": "user", "content": turn.user_text}
        agent = {"role": "assistant", "content": ""}
        start = now_ms()
        async for sentence in self.sentences(build_messages(self.history + [user])):
            first = not turn.reply_text
            if first:
                turn.llm_ms = now_ms() - start
                start = now_ms()
            pcm = await asyncio.to_thread(self.engines.tts.synthesize, sentence, self.s.piper_voice)
            if first:
                turn.tts_ms = now_ms() - start
                self.history += [user, agent]
                self.call.turns.append(turn)
                self.turn = turn
            await self.speak(pcm, sentence, agent)
            if first:
                turn.total_ms = now_ms() - speech_end
            turn.reply_text = f"{turn.reply_text} {sentence}".strip()

    async def sentences(self, messages: list[dict]):
        """Stream the LLM reply and yield each sentence as soon as it is complete."""
        buffer = SentenceBuffer()
        async for piece in self.engines.llm.stream_chat(self.s.llm_model, messages, self.s.llm_max_tokens):
            for sentence in buffer.feed(piece):
                yield sentence
        if rest := buffer.flush():
            yield rest

    async def speak(self, pcm: np.ndarray, sentence: str, message: dict) -> None:
        name = f"m{next(self.mark_ids)}"
        self.marks[name] = (message, sentence)
        self.spoke = True
        await self.send(self.phone.play(pcm_to_ulaw(pcm)))
        await self.send(self.phone.mark(name))
