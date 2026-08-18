'use strict';

const { TtsProvider } = require('./interfaces');

/**
 * Deterministic mock TTS: "synthesizes" a fake audio buffer whose length is
 * a function of the input text, after a short simulated delay. The delay is
 * what makes barge-in testable: if an AbortSignal fires while synthesis is
 * still pending, the promise rejects with an AbortError instead of
 * resolving with audio.
 *
 * A real integration would replace synthesize() with a call to ElevenLabs
 * (or similar) - see README.md for where ELEVENLABS_API_KEY would be read.
 */
class MockTtsProvider extends TtsProvider {
  constructor({ msPerChar = 5, minDelayMs = 10 } = {}) {
    super();
    this.msPerChar = msPerChar;
    this.minDelayMs = minDelayMs;
  }

  async synthesize(text, opts = {}) {
    const { signal } = opts;
    const input = text || '';
    const delay = Math.max(this.minDelayMs, input.length * this.msPerChar);

    if (signal && signal.aborted) {
      const err = new Error('TTS synthesis aborted');
      err.name = 'AbortError';
      throw err;
    }

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        cleanup();
        // Deterministic fake audio buffer: one byte per character, value
        // derived from the character code so output is reproducible.
        const buf = Buffer.alloc(Math.max(1, input.length));
        for (let i = 0; i < input.length; i++) {
          buf[i] = input.charCodeAt(i) % 256;
        }
        resolve({ audio: buf, text: input, durationMs: delay });
      }, delay);

      const onAbort = () => {
        cleanup();
        const err = new Error('TTS synthesis aborted');
        err.name = 'AbortError';
        reject(err);
      };

      function cleanup() {
        clearTimeout(timer);
        if (signal) signal.removeEventListener('abort', onAbort);
      }

      if (signal) signal.addEventListener('abort', onAbort);
    });
  }
}

module.exports = { MockTtsProvider };
