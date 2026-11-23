"""Fake phone calls over the Twilio protocol: test LiveLine without a phone.

Each scripted caller (one per intent) is spoken by a second Piper voice and sent
in real time, one 20 ms frame every 20 ms, with silence between lines.

  reply latency    = caller's last frame sent -> first agent audio received
  barge-in latency = first interrupting frame sent -> "clear" received

  python tools/fake_call.py --calls 50 --barge-in
"""
import argparse
import asyncio
import base64
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

import httpx
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liveline.audio import pcm_to_ulaw          # noqa: E402
from liveline.engines import TextToSpeech      # noqa: E402

SCENARIOS = {   # intent: (caller lines, words one of which the agent must say)
    "book": (["Hi, I would like to book a cleaning appointment.", "My name is Priya Sharma.",
              "Thursday at four in the evening works for me."], ["thursday", "4", "four", "booked"]),
    "reschedule": (["Hello, I need to move my appointment to another day.",
                    "It is Rahul Verma, and my appointment is on Monday.",
                    "Can we make it Wednesday morning instead?"], ["wednesday"]),
    "hours": (["What time are you open on Saturday?", "And where exactly is the clinic?"],
              ["9", "nine", "lake view"]),
    "prices": (["How much does a root canal cost?", "Do you take insurance?"], ["6000", "6,000"]),
    "human": (["Can I please speak to a real person?"], ["transfer", "front desk"]),
}
INTERRUPTION = "Sorry, wait, what are your hours on Saturday?"
FRAME, SILENCE = 160, b"\xff" * 160   # 20 ms of 8 kHz mu-law


class FakeCaller:
    def __init__(self, ws):
        self.ws = ws
        self.sid, self.call_sid = "MZ" + uuid.uuid4().hex, "CA" + uuid.uuid4().hex
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.drained = asyncio.Event()
        self.first_frame_at = self.last_frame_at = self.last_audio_at = self.playing_until = 0.0
        self.first_audio_at = self.clear_at = None
        self.marks: dict[str, asyncio.Task] = {}

    async def sender(self):
        """Like a real phone line: a frame every 20 ms, speech if queued, otherwise silence."""
        next_at = time.perf_counter()
        while True:
            try:
                frame = self.queue.get_nowait()
                self.last_frame_at = time.perf_counter()
                self.first_frame_at = self.first_frame_at or self.last_frame_at
                if self.queue.empty():
                    self.drained.set()
            except asyncio.QueueEmpty:
                frame = SILENCE
            await self.ws.send(json.dumps({"event": "media", "streamSid": self.sid,
                                           "media": {"payload": base64.b64encode(frame).decode()}}))
            next_at += 0.02
            await asyncio.sleep(max(0.0, next_at - time.perf_counter()))

    async def receiver(self):
        """Pretend to play the agent's audio and return each mark when playback reaches it."""
        async for raw in self.ws:
            msg, now = json.loads(raw), time.perf_counter()
            if msg["event"] == "media":
                self.first_audio_at = self.first_audio_at or now
                self.last_audio_at = now
                seconds = len(base64.b64decode(msg["media"]["payload"])) / 8000
                self.playing_until = max(now, self.playing_until) + seconds
            elif msg["event"] == "mark":
                name = msg["mark"]["name"]
                self.marks[name] = asyncio.create_task(self.return_mark(name, self.playing_until - now))
            elif msg["event"] == "clear":
                self.clear_at = self.playing_until = now
                for name, task in list(self.marks.items()):
                    task.cancel()
                    await self.return_mark(name, 0)

    async def return_mark(self, name, delay):
        await asyncio.sleep(max(0.0, delay))
        if self.marks.pop(name, None):
            await self.ws.send(json.dumps({"event": "mark", "streamSid": self.sid, "mark": {"name": name}}))

    async def say(self, ulaw: bytes):
        self.drained.clear()
        for i in range(0, len(ulaw), FRAME):
            await self.queue.put(ulaw[i:i + FRAME].ljust(FRAME, b"\xff"))
        await self.drained.wait()

    async def wait_for_agent(self, timeout=30.0):
        """Done when nothing is playing, no marks are pending and 1.5 s passed with no new audio."""
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            now = time.perf_counter()
            if self.first_audio_at and not self.marks and now >= self.playing_until \
                    and now - self.last_audio_at > 1.5:
                return
            await asyncio.sleep(0.05)


async def run_call(url, intent, tts, voice, barge_in):
    lines = [pcm_to_ulaw(tts.synthesize(line, voice)) for line in SCENARIOS[intent][0]]
    interruption = pcm_to_ulaw(tts.synthesize(INTERRUPTION, voice))
    result = {"intent": intent, "reply_ms": [], "barge_in_ms": None}

    async with websockets.connect(url, max_size=None) as ws:
        c = FakeCaller(ws)
        await ws.send(json.dumps({"event": "start", "streamSid": c.sid, "start": {
            "streamSid": c.sid, "callSid": c.call_sid,
            "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}}}))
        tasks = [asyncio.create_task(c.sender()), asyncio.create_task(c.receiver())]
        await c.wait_for_agent()   # greeting

        for i, line in enumerate(lines):
            c.first_audio_at = None
            await c.say(line)
            spoke_at = c.last_frame_at
            if barge_in and i == 0:
                while c.first_audio_at is None:
                    await asyncio.sleep(0.01)
                result["reply_ms"].append((c.first_audio_at - spoke_at) * 1000)
                await asyncio.sleep(0.8)   # let the agent talk, then interrupt
                c.clear_at = c.first_audio_at = None
                c.first_frame_at = 0.0
                await c.say(interruption)
                if c.first_audio_at and c.first_audio_at < c.last_frame_at:
                    c.first_audio_at = None    # old reply audio sent before the clear
                if c.clear_at:
                    result["barge_in_ms"] = (c.clear_at - c.first_frame_at) * 1000
                spoke_at = c.last_frame_at
            await c.wait_for_agent()
            if c.first_audio_at:
                result["reply_ms"].append((c.first_audio_at - spoke_at) * 1000)

        await ws.send(json.dumps({"event": "stop", "streamSid": c.sid}))
        for task in tasks:
            task.cancel()
    result["call_sid"] = c.call_sid
    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://localhost:8000/twilio/media")
    parser.add_argument("--calls", type=int, default=len(SCENARIOS))
    parser.add_argument("--voice", default="models/en_US-ryan-medium.onnx")
    parser.add_argument("--barge-in", action="store_true")
    args = parser.parse_args()
    api = args.url.replace("ws", "http", 1).split("/twilio")[0]

    tts, intents, results = TextToSpeech(), list(SCENARIOS), []
    for n in range(args.calls):
        r = await run_call(args.url, intents[n % len(intents)], tts, args.voice, args.barge_in)
        results.append(r)
        barge = f"  barge-in {r['barge_in_ms']:.0f} ms" if r["barge_in_ms"] else ""
        print(f"call {n + 1:3d}  {r['intent']:<10}  reply ms: "
              + " ".join(f"{ms:.0f}" for ms in r["reply_ms"]) + barge, flush=True)

    calls = {c["call_id"]: c for c in httpx.get(f"{api}/api/calls", params={"limit": 200}).json()}
    replies = [ms for r in results for ms in r["reply_ms"]]
    barges = [r["barge_in_ms"] for r in results if r["barge_in_ms"]]
    print(f"\n{len(results)} calls, {len(replies)} replies")
    print(f"reply ms: mean {statistics.fmean(replies):.0f}  p50 {statistics.median(replies):.0f}  max {max(replies):.0f}")
    if barges:
        print(f"barge-in ms: mean {statistics.fmean(barges):.0f}  max {max(barges):.0f}")
    for intent in intents:
        mine = [r for r in results if r["intent"] == intent]
        ok = sum(any(w in " ".join(t["reply_text"] for t in calls.get(r["call_sid"], {"turns": []})["turns"]).lower()
                     for w in SCENARIOS[intent][1]) for r in mine)
        print(f"intent {intent:<10} handled {ok}/{len(mine)}")
    print("server stages:", json.dumps(httpx.get(f"{api}/api/summary").json()))


if __name__ == "__main__":
    asyncio.run(main())
