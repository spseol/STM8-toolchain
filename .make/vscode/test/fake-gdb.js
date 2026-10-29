'use strict';
// Stand-in for `stm8-gdb -i dap` in the proxy tests. FAKE selects the behavior:
//   ok           answers everything, `run` ends with a stopped event
//   hang-attach  never answers attach
//   error-run    fails the repl command `run`
//   exit-early   exits at the first request
// Every request is appended to the file FAKE_LOG as one JSON line.
const fs = require('node:fs');
const { encode, createParser } = require('../src/dapframe');

const mode = process.env.FAKE || 'ok';
let seq = 0;
const out = (msg) => process.stdout.write(encode({ seq: ++seq, ...msg }));
const log = (entry) => fs.appendFileSync(process.env.FAKE_LOG, JSON.stringify(entry) + '\n');
const respond = (req, success = true, body = {}, message) =>
  out({ type: 'response', request_seq: req.seq, command: req.command, success, body, ...(message ? { message } : {}) });

const parser = createParser((req) => {
  log({ command: req.command, arguments: req.arguments });
  if (mode === 'exit-early') process.exit(3);
  switch (req.command) {
    case 'initialize':
      respond(req, true, { supportsConfigurationDoneRequest: true });
      out({ type: 'event', event: 'initialized' });
      break;
    case 'attach':
      if (mode !== 'hang-attach') respond(req);
      break;
    case 'evaluate':
      if (req.arguments.expression !== 'run') {
        respond(req, true, { result: 'fake', variablesReference: 0 });
      } else if (mode === 'error-run') {
        respond(req, false, {}, 'Nahrání selhalo: boom');
      } else {
        respond(req, true, { result: '', variablesReference: 0 });
        out({ type: 'event', event: 'stopped', body: { reason: 'breakpoint', threadId: 1 } });
      }
      break;
    case 'disconnect':
      respond(req);
      setTimeout(() => process.exit(0), 20);
      break;
    default:
      respond(req);
  }
});
process.stdin.on('data', (chunk) => parser.push(chunk));
