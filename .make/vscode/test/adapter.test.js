'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { GdbProxy } = require('../src/adapter');

const FAKE = path.join(__dirname, 'fake-gdb.js');
const TARGET = '| openocd -c "gdb_port pipe" 2>/tmp/proj/openocd.log';

async function until(check, ms = 5000) {
  const start = Date.now();
  for (;;) {
    const value = check();
    if (value) return value;
    if (Date.now() - start > ms) throw new Error('timed out waiting for the condition');
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

function setup(t, mode, { project = {}, ...options } = {}) {
  const logFile = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'proxy-')), 'fake.log');
  const sent = [];
  let child;
  const proxy = new GdbProxy({
    project: { elf: '/tmp/proj/out.elf', gdbTarget: TARGET, ...project },
    spawn: () => (child = spawn(process.execPath, [FAKE], { env: { ...process.env, FAKE: mode, FAKE_LOG: logFile } })),
    send: (msg) => sent.push(msg),
    sideEffects: { UART1: ['DR'] },
    stepTimeoutMs: 5000,
    ...options,
  });
  t.after(() => proxy.dispose());
  return {
    proxy,
    sent,
    child: () => child,
    fakeLog: () => (fs.existsSync(logFile) ? fs.readFileSync(logFile, 'utf8').split('\n').filter(Boolean).map(JSON.parse) : []),
    response: (seq) => sent.find((m) => m.type === 'response' && m.request_seq === seq),
    event: (name) => sent.find((m) => m.type === 'event' && m.event === name),
    output: () => sent.filter((m) => m.event === 'output').map((m) => m.body.output).join(''),
  };
}

const request = (seq, command, args) => ({ seq, type: 'request', command, arguments: args });

async function started(t, mode = 'ok', options) {
  const s = setup(t, mode, options);
  s.proxy.handleMessage(request(1, 'initialize', { adapterID: 'stm8' }));
  s.proxy.handleMessage(request(2, 'launch', {}));
  await until(() => s.response(2));
  return s;
}

test('launch_becomes_attach', async (t) => {
  const s = await started(t);
  assert.strictEqual(s.response(2).command, 'launch');
  assert.strictEqual(s.response(2).success, true);
  const commands = s.fakeLog().map((e) => e.command);
  assert.deepStrictEqual(commands, ['initialize', 'attach']);
  const attach = s.fakeLog()[1].arguments;
  assert.strictEqual(attach.program, '"/tmp/proj/out.elf"');
  assert.strictEqual(attach.target, TARGET);
});

test('outgoing_seq_increases', async (t) => {
  const s = await started(t);
  const seqs = s.sent.map((m) => m.seq);
  assert.deepStrictEqual(seqs, [...seqs].sort((a, b) => a - b));
  assert.strictEqual(new Set(seqs).size, seqs.length);
});

test('start_sequence_after_configuration_done', async (t) => {
  const s = await started(t);
  s.proxy.handleMessage(request(3, 'configurationDone'));
  await until(() => s.event('stopped'));
  const log = s.fakeLog();
  const run = log.findIndex((e) => e.command === 'evaluate' && e.arguments.expression === 'run');
  assert.ok(run > log.findIndex((e) => e.command === 'configurationDone'));
  assert.strictEqual(log[run].arguments.context, 'repl');
  assert.strictEqual(s.response(3).success, true);
});

test('step_timeout_terminates', async (t) => {
  const s = setup(t, 'hang-attach', { stepTimeoutMs: 200 });
  s.proxy.handleMessage(request(1, 'initialize', {}));
  s.proxy.handleMessage(request(2, 'launch', {}));
  await until(() => s.event('terminated'));
  assert.match(s.output(), /attach timed out/);
  assert.strictEqual(s.response(2).success, false); // VS Code shows the launch error
  await until(() => s.child().exitCode !== null || s.child().signalCode !== null);
});

test('error_shows_openocd_tail_and_busy_hint', async (t) => {
  const s = setup(t, 'error-run', {
    openocdTail: () => ['Error: libusb_open() failed'],
    otherOpenocd: async () => true,
  });
  s.proxy.handleMessage(request(1, 'initialize', {}));
  s.proxy.handleMessage(request(2, 'launch', {}));
  await until(() => s.response(2));
  s.proxy.handleMessage(request(3, 'configurationDone'));
  await until(() => s.event('terminated'));
  const text = s.output();
  assert.match(text, /run failed: Flashing failed: boom/);
  assert.match(text, /libusb_open\(\) failed/);
  assert.match(text, /ST-Link may be in use by another OpenOCD/);
});

test('no_busy_hint_without_other_openocd', async (t) => {
  const s = setup(t, 'error-run', { otherOpenocd: async () => false });
  s.proxy.handleMessage(request(1, 'initialize', {}));
  s.proxy.handleMessage(request(2, 'launch', {}));
  await until(() => s.response(2));
  s.proxy.handleMessage(request(3, 'configurationDone'));
  await until(() => s.event('terminated'));
  assert.doesNotMatch(s.output(), /in use by another/);
});

test('hover_guard_local_answer', async (t) => {
  const s = await started(t);
  s.proxy.handleMessage(request(9, 'evaluate', { expression: 'UART1->DR', context: 'hover', frameId: 1 }));
  await until(() => s.response(9));
  assert.match(s.response(9).body.result, /not read/);
  assert.match(s.response(9).body.result, /Read icon/); // Watch would read it at every stop
  assert.doesNotMatch(s.response(9).body.result, /Watch/);
  assert.strictEqual(s.response(9).success, true);
  assert.ok(!s.fakeLog().some((e) => e.arguments && e.arguments.expression === 'UART1->DR'));
});

test('hover_other_forwarded', async (t) => {
  const s = await started(t);
  s.proxy.handleMessage(request(9, 'evaluate', { expression: 'GPIOA->ODR', context: 'hover', frameId: 1 }));
  await until(() => s.response(9));
  assert.strictEqual(s.response(9).body.result, 'fake');
  assert.ok(s.fakeLog().some((e) => e.arguments && e.arguments.expression === 'GPIOA->ODR'));
});

test('watch_of_side_effect_register_is_not_guarded', async (t) => {
  const s = await started(t);
  s.proxy.handleMessage(request(9, 'evaluate', { expression: 'UART1->DR', context: 'watch', frameId: 1 }));
  await until(() => s.response(9));
  assert.strictEqual(s.response(9).body.result, 'fake');
});

test('gdb_exit_terminates', async (t) => {
  const s = setup(t, 'exit-early');
  s.proxy.handleMessage(request(1, 'initialize', {}));
  await until(() => s.event('terminated'));
  assert.match(s.output(), /exited unexpectedly/);
});

test('disconnect_is_not_an_error', async (t) => {
  const s = await started(t);
  s.proxy.handleMessage(request(5, 'disconnect', { terminateDebuggee: false }));
  await until(() => s.response(5));
  await until(() => s.child().exitCode !== null);
  await new Promise((resolve) => setTimeout(resolve, 100));
  assert.ok(!s.event('terminated'));
  assert.doesNotMatch(s.output(), /exited unexpectedly/);
});

test('dispose_kills_gdb', async (t) => {
  const s = await started(t);
  s.proxy.dispose();
  await until(() => s.child().exitCode !== null || s.child().signalCode !== null);
});

test('path_with_space_and_diacritics', async (t) => {
  const elf = '/tmp/Žák Novák/lab 1/out.elf';
  const s = await started(t, 'ok', { project: { elf } });
  assert.strictEqual(s.fakeLog()[1].arguments.program, `"${elf}"`); // gdb splits unquoted paths at spaces
});

test('quote_and_backslash_in_path_are_escaped_for_gdb', async (t) => {
  const s = await started(t, 'ok', { project: { elf: '/tmp/a"b\\c/out.elf' } });
  assert.strictEqual(s.fakeLog()[1].arguments.program, '"/tmp/a\\"b\\\\c/out.elf"');
});
