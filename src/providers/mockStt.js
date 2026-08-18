'use strict';

const { SttProvider } = require('./interfaces');

// A small deterministic phrase bank. Real Deepgram/Whisper integrations
// would replace this entirely with an actual audio-to-text call - see
// README.md for where DEEPGRAM_API_KEY would be read.
const PHRASES = [
  'hello there',
  'what is the weather today',
  'can you help me with my order',
  'goodbye thanks',
  'tell me a joke',
];

/**
 * Deterministic mock STT: turns a Buffer of "audio" bytes into text.
 * The mapping is purely a function of the buffer's length and byte sum so
 * that the same input always produces the same transcript, which is what
 * makes the pipeline testable without a real speech model.
 */
class MockSttProvider extends SttProvider {
  async transcribe(audioChunk) {
    if (!Buffer.isBuffer(audioChunk) || audioChunk.length === 0) {
      return '';
    }
    let sum = 0;
    for (const byte of audioChunk) sum += byte;
    const index = (audioChunk.length + sum) % PHRASES.length;
    return PHRASES[index];
  }
}

module.exports = { MockSttProvider, PHRASES };
