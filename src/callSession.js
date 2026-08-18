'use strict';

const { CallStateMachine, STATES } = require('./stateMachine');
const { MockSttProvider } = require('./providers/mockStt');
const { MockLlmProvider } = require('./providers/mockLlm');
const { MockTtsProvider } = require('./providers/mockTts');

/**
 * Orchestrates one phone call: drives the call state machine and runs the
 * STT -> LLM -> TTS pipeline against pluggable providers. Providers default
 * to the deterministic mocks, but any object implementing the interfaces in
 * src/providers/interfaces.js can be passed in instead.
 *
 * Real barge-in handling: if handleAudio() is invoked while a previous
 * call's TTS synthesis is still in flight (state === SPEAKING), the
 * in-flight synthesis is cancelled via AbortController before the new
 * audio is processed.
 */
class CallSession {
  constructor({ stt, llm, tts } = {}) {
    this.stt = stt || new MockSttProvider();
    this.llm = llm || new MockLlmProvider();
    this.tts = tts || new MockTtsProvider();
    this.fsm = new CallStateMachine();
    this._ttsController = null;
  }

  get state() {
    return this.fsm.state;
  }

  /** IDLE -> RINGING */
  ring() {
    this.fsm.transition(STATES.RINGING);
    return this.fsm.state;
  }

  /** IDLE -> RINGING -> CONNECTED -> LISTENING (rings first if needed) */
  connect() {
    if (this.fsm.state === STATES.IDLE) {
      this.fsm.transition(STATES.RINGING);
    }
    this.fsm.transition(STATES.CONNECTED);
    this.fsm.transition(STATES.LISTENING);
    return this.fsm.state;
  }

  /** Any non-ENDED state -> ENDED. Cancels any in-flight TTS. */
  hangup() {
    if (this._ttsController) {
      this._ttsController.abort();
      this._ttsController = null;
    }
    if (!this.fsm.isEnded()) {
      this.fsm.transition(STATES.ENDED);
    }
    return this.fsm.state;
  }

  /**
   * Feed one chunk of caller audio through the pipeline. If TTS is
   * currently speaking, this triggers barge-in: the in-flight synthesis is
   * aborted and that earlier call resolves with { cancelled: true }.
   *
   * @returns {Promise<{ cancelled: true } | { cancelled: false, transcript: string, reply: string, audio: Buffer }>}
   */
  async handleAudio(audioChunk) {
    if (this.fsm.state === STATES.SPEAKING) {
      this._bargeIn();
    }
    if (this.fsm.state === STATES.CONNECTED) {
      this.fsm.transition(STATES.LISTENING);
    }
    if (this.fsm.state !== STATES.LISTENING) {
      throw new Error(`Cannot handle audio while in state ${this.fsm.state}`);
    }

    const transcript = await this.stt.transcribe(audioChunk);
    this.fsm.transition(STATES.THINKING);

    const reply = await this.llm.generate(transcript);
    this.fsm.transition(STATES.SPEAKING);

    const controller = new AbortController();
    this._ttsController = controller;

    try {
      const result = await this.tts.synthesize(reply, { signal: controller.signal });
      // Only advance the state machine if we're still the active TTS call -
      // a later handleAudio() may have already barged in and moved on.
      if (this._ttsController === controller) {
        this._ttsController = null;
        this.fsm.transition(STATES.LISTENING);
      }
      return { cancelled: false, transcript, reply, audio: result.audio };
    } catch (err) {
      if (err.name === 'AbortError') {
        return { cancelled: true, transcript, reply };
      }
      throw err;
    }
  }

  /** Cancel in-flight TTS (if any) and move SPEAKING -> LISTENING. */
  _bargeIn() {
    if (this._ttsController) {
      this._ttsController.abort();
      this._ttsController = null;
    }
    this.fsm.transition(STATES.LISTENING);
  }
}

module.exports = { CallSession };
