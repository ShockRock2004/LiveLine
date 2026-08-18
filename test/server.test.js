'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const WebSocket = require('ws');
const { createServer } = require('../src/server');

test('WebSocket server accepts a connection and responds to an audio frame', async () => {
  const wss = createServer({ port: 0 });
  const { port } = wss.address();

  const client = new WebSocket(`ws://localhost:${port}`);

  await new Promise((resolve, reject) => {
    client.on('open', resolve);
    client.on('error', reject);
  });

  const messagePromise = new Promise((resolve, reject) => {
    client.on('message', (data) => {
      try {
        resolve(JSON.parse(data.toString()));
      } catch (err) {
        reject(err);
      }
    });
    client.on('error', reject);
  });

  client.send(Buffer.from([1, 2, 3, 4]));

  const message = await messagePromise;
  assert.equal(message.type, 'pipeline_result');
  assert.equal(message.cancelled, false);
  assert.equal(typeof message.transcript, 'string');
  assert.equal(typeof message.reply, 'string');

  client.close();
  await new Promise((resolve) => wss.close(resolve));
});
