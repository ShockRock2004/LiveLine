"""Twilio Media Streams and Plivo Audio Streams behind one interface: parse, play, mark, clear."""
import base64
import json
from dataclasses import dataclass


@dataclass
class Inbound:
    kind: str           # start, audio, played, stop or other
    call_id: str = ""
    audio: bytes = b""  # 8 kHz mu-law
    mark: str = ""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


class Twilio:
    name = "twilio"
    sid = ""

    def parse(self, raw: str) -> Inbound:
        msg = json.loads(raw)
        event = msg.get("event")
        if event == "start":
            self.sid = msg["start"]["streamSid"]
            return Inbound("start", call_id=msg["start"]["callSid"])
        if event == "media":
            return Inbound("audio", audio=base64.b64decode(msg["media"]["payload"]))
        if event == "mark":
            return Inbound("played", mark=msg["mark"]["name"])
        return Inbound("stop" if event == "stop" else "other")

    def play(self, ulaw: bytes) -> str:
        return json.dumps({"event": "media", "streamSid": self.sid, "media": {"payload": _b64(ulaw)}})

    def mark(self, name: str) -> str:
        return json.dumps({"event": "mark", "streamSid": self.sid, "mark": {"name": name}})

    def clear(self) -> str:
        return json.dumps({"event": "clear", "streamSid": self.sid})

    @staticmethod
    def answer(ws_url: str) -> str:
        return ('<?xml version="1.0" encoding="UTF-8"?>'
                f'<Response><Connect><Stream url="{ws_url}"/></Connect></Response>')


class Plivo:
    name = "plivo"
    sid = ""

    def parse(self, raw: str) -> Inbound:
        msg = json.loads(raw)
        event = msg.get("event")
        if event == "start":
            self.sid = msg["start"]["streamId"]
            return Inbound("start", call_id=msg["start"]["callId"])
        if event == "media":
            return Inbound("audio", audio=base64.b64decode(msg["media"]["payload"]))
        if event == "playedStream":
            return Inbound("played", mark=msg["name"])
        return Inbound("stop" if event == "stop" else "other")

    def play(self, ulaw: bytes) -> str:
        return json.dumps({"event": "playAudio", "media": {
            "contentType": "audio/x-mulaw", "sampleRate": 8000, "payload": _b64(ulaw)}})

    def mark(self, name: str) -> str:
        return json.dumps({"event": "checkpoint", "streamId": self.sid, "name": name})

    def clear(self) -> str:
        return json.dumps({"event": "clearAudio", "streamId": self.sid})

    @staticmethod
    def answer(ws_url: str) -> str:
        return ('<?xml version="1.0" encoding="UTF-8"?><Response>'
                '<Stream bidirectional="true" keepCallAlive="true" '
                f'contentType="audio/x-mulaw;rate=8000">{ws_url}</Stream></Response>')
