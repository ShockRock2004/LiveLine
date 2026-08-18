'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { CallStateMachine, STATES, InvalidTransitionError } = require('../src/stateMachine');

test('starts in IDLE', () => {
  const fsm = new CallStateMachine();
  assert.equal(fsm.state, STATES.IDLE);
});

test('walks the full happy-path lifecycle', () => {
  const fsm = new CallStateMachine();
  fsm.transition(STATES.RINGING);
  fsm.transition(STATES.CONNECTED);
  fsm.transition(STATES.LISTENING);
  fsm.transition(STATES.THINKING);
  fsm.transition(STATES.SPEAKING);
  assert.equal(fsm.state, STATES.SPEAKING);
  fsm.transition(STATES.ENDED);
  assert.equal(fsm.state, STATES.ENDED);
  assert.equal(fsm.isEnded(), true);
});

test('allows the SPEAKING -> LISTENING barge-in transition', () => {
  const fsm = new CallStateMachine();
  fsm.transition(STATES.RINGING);
  fsm.transition(STATES.CONNECTED);
  fsm.transition(STATES.LISTENING);
  fsm.transition(STATES.THINKING);
  fsm.transition(STATES.SPEAKING);
  fsm.transition(STATES.LISTENING);
  assert.equal(fsm.state, STATES.LISTENING);
});

test('rejects skipping states', () => {
  const fsm = new CallStateMachine();
  assert.throws(() => fsm.transition(STATES.CONNECTED), InvalidTransitionError);
  assert.throws(() => fsm.transition(STATES.SPEAKING), InvalidTransitionError);
  // state must not have moved
  assert.equal(fsm.state, STATES.IDLE);
});

test('rejects transitions out of ENDED', () => {
  const fsm = new CallStateMachine();
  fsm.transition(STATES.RINGING);
  fsm.transition(STATES.ENDED);
  assert.throws(() => fsm.transition(STATES.RINGING), InvalidTransitionError);
  assert.throws(() => fsm.transition(STATES.CONNECTED), InvalidTransitionError);
});

test('canTransition reports validity without mutating state', () => {
  const fsm = new CallStateMachine();
  assert.equal(fsm.canTransition(STATES.RINGING), true);
  assert.equal(fsm.canTransition(STATES.CONNECTED), false);
  assert.equal(fsm.state, STATES.IDLE);
});

test('rejects unknown target states', () => {
  const fsm = new CallStateMachine();
  assert.throws(() => fsm.transition('NOT_A_REAL_STATE'));
});

test('history records every accepted transition in order', () => {
  const fsm = new CallStateMachine();
  fsm.transition(STATES.RINGING);
  fsm.transition(STATES.CONNECTED);
  assert.deepEqual(fsm.history, [STATES.IDLE, STATES.RINGING, STATES.CONNECTED]);
});
