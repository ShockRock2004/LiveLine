import base64
import json

from liveline.telephony import Plivo, Twilio


def test_twilio():
    p = Twilio()
    start = p.parse(json.dumps({"event": "start", "start": {"streamSid": "MZ1", "callSid": "CA1"}}))
    assert (start.kind, start.call_id, p.sid) == ("start", "CA1", "MZ1")
    media = {"event": "media", "media": {"payload": base64.b64encode(b"\x01\x02").decode()}}
    assert p.parse(json.dumps(media)).audio == b"\x01\x02"
    assert p.parse(json.dumps({"event": "mark", "mark": {"name": "m3"}})).mark == "m3"
    assert p.parse(json.dumps({"event": "stop"})).kind == "stop"
    assert json.loads(p.play(b"\xff")) == {"event": "media", "streamSid": "MZ1", "media": {"payload": "/w=="}}
    assert json.loads(p.mark("m1")) == {"event": "mark", "streamSid": "MZ1", "mark": {"name": "m1"}}
    assert json.loads(p.clear()) == {"event": "clear", "streamSid": "MZ1"}
    assert '<Stream url="wss://x/twilio/media"/>' in Twilio.answer("wss://x/twilio/media")


def test_plivo():
    p = Plivo()
    start = p.parse(json.dumps({"event": "start", "start": {"streamId": "S1", "callId": "C1"}}))
    assert (start.kind, start.call_id, p.sid) == ("start", "C1", "S1")
    assert p.parse(json.dumps({"event": "playedStream", "name": "m2"})).mark == "m2"
    assert json.loads(p.play(b"\xff"))["media"]["contentType"] == "audio/x-mulaw"
    assert json.loads(p.mark("m1")) == {"event": "checkpoint", "streamId": "S1", "name": "m1"}
    assert json.loads(p.clear()) == {"event": "clearAudio", "streamId": "S1"}
    assert 'bidirectional="true"' in Plivo.answer("wss://x/plivo/media")
