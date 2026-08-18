'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { CallSession } = require('../src/callSession');
const { MockSttProvider, PHRASES } = require('../src/providers/mockStt');
const { MockLlmProvider, DEFAULT_REPLY } = require('../src/providers/mockLlm');
const { MockTtsProvider } = require('../src/providers/mockTts');
const { STATES } = require('../src/stateMachine');

test('MockSttProvider is deterministic for a given buffer', async () => {
  const stt = new MockSttProvider();
  const chunk = Buffer.from([1, 2, 3, 4, 5]);
  const a = await stt.transcribe(chunk);
  const b = await stt.transcribe(Buffer.from(chunk)); // fresh copy, same bytes
  assert.equal(a, b);
  assert.ok(PHRASES.includes(a));
});

test('MockSttProvider returns empty string for empty input', async () => {
  const stt = new MockSttProvider();
  assert.equal(await stt.transcribe(Buffer.alloc(0)), '');
});

test('MockLlmProvider gives rule-based replies and a default fallback', async () => {
  const llm = new MockLlmProvider();
  assert.match(await llm.generate('hello there'), /Hi! How can I help/);
  assert.match(await llm.generate('tell me a joke please'), /developer/i);
  assert.equal(await llm.generate('asdlkfjasldkfj'), DEFAULT_REPLY);
});

test('MockTtsProvider produces a deterministic-length buffer', async () => {
  const tts = new MockTtsProvider({ msPerChar: 1, minDelayMs: 1 });
  const result = await tts.synthesize('hi');
  assert.ok(Buffer.isBuffer(result.audio));
  assert.equal(result.audio.length, 2);
});

test('end-to-end pipeline: audio in -> transcript -> reply -> synthesized audio out', async () => {
  const session = new CallSession({ tts: new MockTtsProvider({ msPerChar: 1, minDelayMs: 1 }) });

  session.ring();
  assert.equal(session.state, STATES.RINGING);
  session.connect();
  assert.equal(session.state, STATES.LISTENING);

  const audioChunk = Buffer.from([10, 20, 30]); // deterministic fake "audio"
  const expectedTranscript = await new MockSttProvider().transcribe(audioChunk);
  const expectedReply = await new MockLlmProvider().generate(expectedTranscript);

  const result = await session.handleAudio(audioChunk);

  assert.equal(result.cancelled, false);
  assert.equal(result.transcript, expectedTranscript);
  assert.equal(result.reply, expectedReply);
  assert.ok(Buffer.isBuffer(result.audio));
  assert.equal(result.audio.length, expectedReply.length);
  assert.equal(session.state, STATES.LISTENING);

  session.hangup();
  assert.equal(session.state, STATES.ENDED);
});

test('handleAudio rejects when called from a state that cannot accept audio', async () => {
  const session = new CallSession();
  // Never rang/connected - still IDLE.
  await assert.rejects(session.handleAudio(Buffer.from([1])));
});
