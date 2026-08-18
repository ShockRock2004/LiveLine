'use strict';

/**
 * Provider interfaces. These are the seams where real vendor SDKs would be
 * plugged in (see README.md for exactly how). Nothing in this repo calls a
 * real API - every provider used by tests and the server is the deterministic
 * mock implementation living alongside this file.
 */

/** Speech-to-text provider interface. */
class SttProvider {
  // eslint-disable-next-line no-unused-vars
  async transcribe(audioChunk) {
    throw new Error('SttProvider.transcribe must be implemented by a subclass');
  }
}

/** Text generation ("LLM") provider interface. */
class LlmProvider {
  // eslint-disable-next-line no-unused-vars
  async generate(text, context) {
    throw new Error('LlmProvider.generate must be implemented by a subclass');
  }
}

/** Text-to-speech provider interface. */
class TtsProvider {
  /**
   * @param {string} text
   * @param {{ signal?: AbortSignal }} opts - opts.signal allows callers to
   *   cancel in-flight synthesis (used for barge-in interruption).
   */
  // eslint-disable-next-line no-unused-vars
  async synthesize(text, opts) {
    throw new Error('TtsProvider.synthesize must be implemented by a subclass');
  }
}

module.exports = { SttProvider, LlmProvider, TtsProvider };
