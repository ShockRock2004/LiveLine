'use strict';

const { LlmProvider } = require('./interfaces');

// A tiny rule-based response table. A real integration would replace
// generate() with a call to GPT-4o-mini (or similar) - see README.md for
// where OPENAI_API_KEY would be read.
const RULES = [
  { match: /hello|hi there/i, reply: 'Hi! How can I help you today?' },
  { match: /weather/i, reply: "I don't have live weather data, but it sounds nice out." },
  { match: /order/i, reply: 'Sure, I can help with your order. Could you give me the order number?' },
  { match: /goodbye|bye/i, reply: 'Goodbye, have a great day!' },
  { match: /joke/i, reply: 'Why did the developer go broke? Because they used up all their cache.' },
];

const DEFAULT_REPLY = "Sorry, I didn't quite catch that. Could you repeat it?";

/**
 * Deterministic mock LLM: matches the transcript against a small rule table
 * and returns a canned reply. No network calls, no randomness.
 */
class MockLlmProvider extends LlmProvider {
  async generate(text) {
    const input = text || '';
    for (const rule of RULES) {
      if (rule.match.test(input)) {
        return rule.reply;
      }
    }
    return DEFAULT_REPLY;
  }
}

module.exports = { MockLlmProvider, RULES, DEFAULT_REPLY };
