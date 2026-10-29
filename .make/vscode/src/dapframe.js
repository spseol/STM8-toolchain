'use strict';

/** One DAP message as bytes. Content-Length counts bytes, not characters. */
function encode(msg) {
  const body = Buffer.from(JSON.stringify(msg), 'utf8');
  return Buffer.concat([Buffer.from(`Content-Length: ${body.length}\r\n\r\n`, 'ascii'), body]);
}

/** Collects stream chunks and calls onMessage(msg) for every complete DAP message. */
function createParser(onMessage) {
  let buffer = Buffer.alloc(0);
  return {
    push(chunk) {
      buffer = Buffer.concat([buffer, chunk]);
      for (;;) {
        const headerEnd = buffer.indexOf('\r\n\r\n');
        if (headerEnd < 0) return;
        const match = /Content-Length: *(\d+)/i.exec(buffer.subarray(0, headerEnd).toString('ascii'));
        const bodyStart = headerEnd + 4;
        if (!match) { // stray text before a header: drop it
          buffer = buffer.subarray(bodyStart);
          continue;
        }
        const bodyEnd = bodyStart + Number(match[1]);
        if (buffer.length < bodyEnd) return;
        const body = buffer.subarray(bodyStart, bodyEnd).toString('utf8');
        buffer = buffer.subarray(bodyEnd);
        onMessage(JSON.parse(body));
      }
    },
  };
}

module.exports = { encode, createParser };
