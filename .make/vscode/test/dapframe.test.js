'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { encode, createParser } = require('../src/dapframe');

function collect() {
  const received = [];
  return { received, parser: createParser((msg) => received.push(msg)) };
}

test('split_in_three_chunks', () => {
  const msg = { seq: 1, type: 'event', event: 'stopped', body: { reason: 'breakpoint' } };
  const buf = encode(msg);
  const { received, parser } = collect();
  parser.push(buf.subarray(0, 5));
  parser.push(buf.subarray(5, 20));
  assert.deepStrictEqual(received, []);
  parser.push(buf.subarray(20));
  assert.deepStrictEqual(received, [msg]);
});

test('utf8_char_split_across_chunks', () => {
  const msg = { seq: 2, type: 'event', event: 'output', body: { output: 'Žák Novák\n' } };
  const buf = encode(msg);
  const cut = buf.indexOf(Buffer.from('Ž', 'utf8')) + 1; // between the two bytes of Ž
  const { received, parser } = collect();
  parser.push(buf.subarray(0, cut));
  parser.push(buf.subarray(cut));
  assert.deepStrictEqual(received, [msg]);
});

test('two_messages_in_one_chunk', () => {
  const a = { seq: 1, type: 'response' };
  const b = { seq: 2, type: 'event', event: 'continued' };
  const { received, parser } = collect();
  parser.push(Buffer.concat([encode(a), encode(b)]));
  assert.deepStrictEqual(received, [a, b]);
});

test('content_length_counts_bytes', () => {
  const msg = { text: 'ž' };
  const buf = encode(msg);
  const json = JSON.stringify(msg);
  assert.ok(Buffer.byteLength(json) > json.length);
  assert.ok(buf.toString('utf8').startsWith(`Content-Length: ${Buffer.byteLength(json)}\r\n\r\n`));
});
