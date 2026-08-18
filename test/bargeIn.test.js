'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { CallSession } = require('../src/callSession');
const { MockTtsProvider } = require('../src/providers/mockTts');
const { STATES } = require('../src/stateMachine');

function tick(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

test('MockTtsProvider rejects with AbortError when its signal fires mid-synthesis', async () => {
  const tts = new MockTtsProvider({ msPerChar: 5, minDelayMs: 50 });
  const controller = new AbortController();
  const promise = tts.synthesize('this will be interrupted', { signal: controller.signal });

  await tick(5); // let synthesis start but not finish
  controller.abort();

  await assert.rejects(promise, (err) => err.name === 'AbortError');
});

test('new audio arriving while TTS is speaking cancels the in-flight TTS (barge-in)', async () => {
  const session = new CallSession({ tts: new MockTtsProvider({ msPerChar: 8, minDelayMs: 50 }) });
  session.connect();

  const firstAudio = Buffer.from([1, 2, 3, 4]); // -> "hello there" -> greeting reply
  const secondAudio = Buffer.from([9, 9, 9, 9, 9]); // -> different transcript

  const firstResultPromise = session.handleAudio(firstAudio);

  // Give the pipeline time to run STT + LLM and reach SPEAKING with TTS in flight.
  await tick(10);
  assert.equal(session.state, STATES.SPEAKING);

  const secondResultPromise = session.handleAudio(secondAudio);

  const [firstResult, secondResult] = await Promise.all([firstResultPromise, secondResultPromise]);

  assert.equal(firstResult.cancelled, true, 'first (in-flight) TTS should have been cancelled by barge-in');
  assert.equal(secondResult.cancelled, false, 'second request should complete normally');
  assert.ok(Buffer.isBuffer(secondResult.audio));
  assert.equal(session.state, STATES.LISTENING);
});

test('without barge-in, sequential calls both complete normally', async () => {
  const session = new CallSession({ tts: new MockTtsProvider({ msPerChar: 1, minDelayMs: 5 }) });
  session.connect();

  const first = await session.handleAudio(Buffer.from([1, 2, 3]));
  assert.equal(first.cancelled, false);
  assert.equal(session.state, STATES.LISTENING);

  const second = await session.handleAudio(Buffer.from([4, 5, 6]));
  assert.equal(second.cancelled, false);
  assert.equal(session.state, STATES.LISTENING);
});

test('hangup during SPEAKING cancels TTS and ends the call', async () => {
  const session = new CallSession({ tts: new MockTtsProvider({ msPerChar: 20, minDelayMs: 100 }) });
  session.connect();

  const resultPromise = session.handleAudio(Buffer.from([1, 2, 3]));
  await tick(10);
  assert.equal(session.state, STATES.SPEAKING);

  session.hangup();
  assert.equal(session.state, STATES.ENDED);

  const result = await resultPromise;
  assert.equal(result.cancelled, true);
});
