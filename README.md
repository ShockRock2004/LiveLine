# voice-ai-phone-agent

A small, honest portfolio project demonstrating the architecture of a voice
AI phone agent: a real WebSocket server for streaming audio, a real call
lifecycle state machine, real barge-in (interruption) handling, and a
pluggable STT -> LLM -> TTS pipeline. **The speech-to-text, language model,
and text-to-speech providers are deterministic mocks**, not real API
integrations. This project has never made a real Deepgram, OpenAI, or
ElevenLabs API call.

## What's real vs. what's mocked

| Piece | Status |
|---|---|
| WebSocket server (`src/server.js`) | Real. Uses the `ws` package to accept connections and binary frames. |
| Call state machine (`src/stateMachine.js`) | Real. Enforces legal transitions and throws on illegal ones. |
| Barge-in / interruption logic (`src/callSession.js`) | Real. Uses a real `AbortController` to cancel in-flight TTS synthesis when new audio arrives. |
| Provider *interfaces* (`src/providers/interfaces.js`) | Real (just interfaces/contracts, no implementation). |
| STT provider (`src/providers/mockStt.js`) | **Mock.** Deterministically maps a buffer's length/byte-sum to a canned phrase. No audio decoding, no network call. |
| LLM provider (`src/providers/mockLlm.js`) | **Mock.** Rule-based regex matching against a canned reply table, plus a default fallback. No model, no network call. |
| TTS provider (`src/providers/mockTts.js`) | **Mock.** Returns a fake `Buffer` after a short simulated (but real, cancellable) delay. No audio synthesis, no network call. |

Nothing in this repo requires, reads, or calls out with a real API key. It
runs fully offline.

## Architecture

```
 WebSocket client
        │  binary audio frames
        ▼
 src/server.js  ──creates one──▶  CallSession (src/callSession.js)
                                        │
                         drives a CallStateMachine (src/stateMachine.js)
                                        │
                     IDLE→RINGING→CONNECTED→LISTENING→THINKING→SPEAKING→ENDED
                                        │
                    ┌───────────────────┼────────────────────┐
                    ▼                   ▼                    ▼
             SttProvider          LlmProvider           TtsProvider
          (interfaces.js)       (interfaces.js)       (interfaces.js)
                    │                   │                    │
             MockSttProvider     MockLlmProvider       MockTtsProvider
```

### Call state machine

States: `IDLE`, `RINGING`, `CONNECTED`, `LISTENING`, `THINKING`, `SPEAKING`,
`ENDED`.

Only these transitions are legal:

- `IDLE → RINGING`
- `RINGING → CONNECTED | ENDED`
- `CONNECTED → LISTENING | ENDED`
- `LISTENING → THINKING | ENDED`
- `THINKING → SPEAKING | ENDED`
- `SPEAKING → LISTENING | ENDED` (the `SPEAKING → LISTENING` edge is the
  barge-in path)

Any other transition throws `InvalidTransitionError`. See
`test/stateMachine.test.js` for the full set of valid/invalid cases.

### Barge-in / interruption

`CallSession.handleAudio()` creates an `AbortController` before starting TTS
synthesis and passes its `signal` to the provider. If `handleAudio()` is
called again while the session is still `SPEAKING` (i.e. TTS is in flight),
it immediately calls `controller.abort()` on the previous synthesis and
transitions the state machine `SPEAKING → LISTENING` before processing the
new audio. The interrupted call's promise resolves with `{ cancelled: true
}` instead of throwing, so callers can distinguish "this got barged in on"
from a real error. See `test/bargeIn.test.js`.

### Pipeline

`CallSession.handleAudio(audioChunk)`:

1. `stt.transcribe(audioChunk)` → transcript
2. `llm.generate(transcript)` → reply text
3. `tts.synthesize(reply, { signal })` → `{ audio: Buffer, ... }`

Each stage is behind the interfaces in `src/providers/interfaces.js`:

```js
class SttProvider { async transcribe(audioChunk) {} }
class LlmProvider { async generate(text, context) {} }
class TtsProvider { async synthesize(text, { signal }) {} }
```

## Plugging in real providers (not done here)

This repo intentionally stops at the interface boundary. To wire in real
vendors, you would implement each interface as a subclass and swap it in
where `CallSession` is constructed (`src/callSession.js` / `src/server.js`
default to the mocks). None of this is implemented or tested in this repo -
it's documented here so the seam is obvious:

- **STT — Deepgram**: implement `SttProvider.transcribe(audioChunk)` to open
  a Deepgram streaming/pre-recorded transcription request, reading the API
  key from `process.env.DEEPGRAM_API_KEY`, and return the resulting text.
- **LLM — GPT-4o-mini**: implement `LlmProvider.generate(text, context)` to
  call the OpenAI chat completions API with `model: "gpt-4o-mini"`, reading
  the key from `process.env.OPENAI_API_KEY`, and return the completion text.
- **TTS — ElevenLabs**: implement `TtsProvider.synthesize(text, { signal })`
  to call the ElevenLabs text-to-speech API, reading the key from
  `process.env.ELEVENLABS_API_KEY`, forward `signal` to whatever HTTP client
  is used (e.g. `fetch(url, { signal })`) so barge-in still cancels the
  request, and return the resulting audio buffer.

No such calls exist in the current code, and no `.env` file or secret is
included or required to run or test this project.

## Tech stack

- Node.js (CommonJS)
- [`ws`](https://www.npmjs.com/package/ws) for the WebSocket server — the
  only runtime dependency
- Node's built-in `node:test` + `node:assert/strict` for unit tests — no
  test framework dependency needed

## Running it

```bash
npm install
npm test          # runs all unit tests (state machine, barge-in, pipeline, server)
npm start          # starts the WebSocket server on ws://localhost:8080
```

Once the server is running, any WebSocket client can connect and send
binary frames; the server replies with a JSON message describing the
pipeline result (transcript, reply, and whether it was cancelled by
barge-in):

```json
{ "type": "pipeline_result", "state": "LISTENING", "cancelled": false, "transcript": "hello there", "reply": "Hi! How can I help you today?" }
```

## Project layout

```
src/
  stateMachine.js        # real call lifecycle state machine
  callSession.js          # real pipeline orchestration + barge-in
  server.js               # real WebSocket server
  providers/
    interfaces.js         # SttProvider / LlmProvider / TtsProvider contracts
    mockStt.js             # deterministic mock STT
    mockLlm.js             # deterministic mock LLM
    mockTts.js             # deterministic mock TTS with abort support
test/
  stateMachine.test.js
  bargeIn.test.js
  pipeline.test.js
  server.test.js
```

## License

MIT — see [LICENSE](./LICENSE).
