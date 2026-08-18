'use strict';

/**
 * Call lifecycle states.
 */
const STATES = Object.freeze({
  IDLE: 'IDLE',
  RINGING: 'RINGING',
  CONNECTED: 'CONNECTED',
  LISTENING: 'LISTENING',
  THINKING: 'THINKING',
  SPEAKING: 'SPEAKING',
  ENDED: 'ENDED',
});

// Map of state -> set of states it may legally transition to.
const TRANSITIONS = Object.freeze({
  [STATES.IDLE]: [STATES.RINGING],
  [STATES.RINGING]: [STATES.CONNECTED, STATES.ENDED],
  [STATES.CONNECTED]: [STATES.LISTENING, STATES.ENDED],
  [STATES.LISTENING]: [STATES.THINKING, STATES.ENDED],
  [STATES.THINKING]: [STATES.SPEAKING, STATES.ENDED],
  // SPEAKING can go back to LISTENING: this is the barge-in path, where
  // new caller audio interrupts in-flight TTS playback.
  [STATES.SPEAKING]: [STATES.LISTENING, STATES.ENDED],
  [STATES.ENDED]: [],
});

class InvalidTransitionError extends Error {
  constructor(from, to) {
    super(`Invalid call state transition: ${from} -> ${to}`);
    this.name = 'InvalidTransitionError';
    this.from = from;
    this.to = to;
  }
}

/**
 * A small, explicit state machine describing the lifecycle of a phone call.
 * This is real logic (not mocked): it enforces which transitions are legal
 * and rejects everything else.
 */
class CallStateMachine {
  constructor(initial = STATES.IDLE) {
    if (!TRANSITIONS[initial]) {
      throw new Error(`Unknown initial state: ${initial}`);
    }
    this._state = initial;
    this._history = [initial];
  }

  get state() {
    return this._state;
  }

  get history() {
    return this._history.slice();
  }

  canTransition(to) {
    const allowed = TRANSITIONS[this._state] || [];
    return allowed.includes(to);
  }

  /**
   * Attempt to move to a new state. Throws InvalidTransitionError if the
   * transition isn't allowed from the current state.
   */
  transition(to) {
    if (!TRANSITIONS[to]) {
      throw new Error(`Unknown target state: ${to}`);
    }
    if (!this.canTransition(to)) {
      throw new InvalidTransitionError(this._state, to);
    }
    this._state = to;
    this._history.push(to);
    return this._state;
  }

  isEnded() {
    return this._state === STATES.ENDED;
  }
}

module.exports = { CallStateMachine, STATES, InvalidTransitionError };
