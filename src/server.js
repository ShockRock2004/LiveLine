'use strict';

const { WebSocketServer } = require('ws');
const { CallSession } = require('./callSession');

/**
 * A real WebSocket server that accepts streaming "audio" frames per
 * connection and drives a CallSession per socket. Each binary (or base64
 * text) message received is treated as one audio chunk. There is no real
 * audio codec handling here - frames are opaque byte buffers, which is
 * sufficient to exercise the pipeline and barge-in logic end to end.
 *
 * Protocol (intentionally minimal):
 *  - Client connects -> server creates a CallSession and rings/connects it.
 *  - Client sends a binary frame -> treated as one audio chunk, fed into
 *    session.handleAudio(). If TTS was speaking, this triggers barge-in.
 *  - Server replies with a JSON text frame describing the pipeline result.
 *  - Client disconnects -> session.hangup() is called.
 */
function createServer({ port = 0 } = {}) {
  const wss = new WebSocketServer({ port });

  wss.on('connection', (socket) => {
    const session = new CallSession();
    session.ring();
    session.connect();

    socket.on('message', async (data, isBinary) => {
      const chunk = isBinary || Buffer.isBuffer(data) ? Buffer.from(data) : Buffer.from(String(data), 'base64');
      try {
        const result = await session.handleAudio(chunk);
        socket.send(JSON.stringify({ type: 'pipeline_result', state: session.state, ...result, audio: undefined }));
      } catch (err) {
        socket.send(JSON.stringify({ type: 'error', message: err.message }));
      }
    });

    socket.on('close', () => {
      session.hangup();
    });
  });

  return wss;
}

if (require.main === module) {
  const port = Number(process.env.PORT) || 8080;
  const wss = createServer({ port });
  // eslint-disable-next-line no-console
  console.log(`voice-ai-phone-agent WebSocket server listening on ws://localhost:${port}`);
  wss.on('error', (err) => {
    // eslint-disable-next-line no-console
    console.error('Server error:', err);
  });
}

module.exports = { createServer };
