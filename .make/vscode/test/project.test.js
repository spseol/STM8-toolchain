'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { readProjectInfo, openocdTail, otherOpenocd } = require('../src/project');

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'project-'));

test('read_project_info_parses_json_and_forces_english_make', async () => {
  const info = { device: 'STM8S208', elf: '/p/out.elf' };
  let call;
  const exec = async (cmd, args, options) => {
    call = { cmd, args, options };
    return { stdout: `${JSON.stringify(info)}\n` };
  };
  assert.deepStrictEqual(await readProjectInfo('/p', { exec }), info);
  assert.deepStrictEqual(call.args, ['-s', '--no-print-directory', 'dap-info']);
  assert.strictEqual(call.options.cwd, '/p');
  assert.strictEqual(call.options.env.LC_ALL, 'C');
});

test('openocd_tail_last_five_errors', () => {
  const log = path.join(tmp(), 'openocd.log');
  const lines = [];
  for (let i = 1; i <= 8; i++) lines.push(`Error: problem ${i}`, `Info : fine ${i}`);
  fs.writeFileSync(log, lines.join('\n'));
  assert.deepStrictEqual(openocdTail(log), [4, 5, 6, 7, 8].map((i) => `Error: problem ${i}`));
});

test('openocd_tail_missing_log_is_empty', () => {
  assert.deepStrictEqual(openocdTail(path.join(tmp(), 'nope.log')), []);
});

test('other_openocd_true_when_pgrep_finds_one', async () => {
  assert.strictEqual(await otherOpenocd({ exec: async () => ({ stdout: '1234\n' }) }), true);
});

test('other_openocd_false_when_pgrep_finds_none', async () => {
  const exec = async () => {
    throw Object.assign(new Error('exit 1'), { code: 1 });
  };
  assert.strictEqual(await otherOpenocd({ exec }), false);
});

// --- Task 9: errors, preflight, version notice -------------------------------------------

const { ToolchainError, makefileConflictError, preflight, versionNotice, upgradeOffer } = require('../src/project');

const rejecting = (stderr, code = 2) => async () => {
  throw Object.assign(new Error('make failed'), { stderr, code });
};

test('old_toolchain_message', async () => {
  await assert.rejects(
    readProjectInfo('/p', { exec: rejecting("make: *** No rule to make target 'dap-info'.  Stop.") }),
    (error) => error instanceof ToolchainError
      && /Old toolchain – run STM8: Update Toolchain \(or update \.make\/ by hand and add the line -include \.make\/vscode\.mk to Makefile\)/.test(error.message)
      && error.fix === 'updateToolchain',
  );
});

test('other_toolchain_errors_have_no_fix', async () => {
  await assert.rejects(
    readProjectInfo('/p', { exec: rejecting('Makefile:181: *** boom.  Stop.') }),
    (error) => error instanceof ToolchainError && error.fix === undefined,
  );
});

test('unresolved_conflict_in_makefile_stops_before_make_runs', async () => {
  const dir = tmp();
  fs.writeFileSync(path.join(dir, 'Makefile'), 'A=1\n<<<<<<< Makefile\nB=2\n=======\nB=3\n>>>>>>> FETCH_HEAD\n');
  let called = false;
  const exec = async () => { called = true; return { stdout: '{}' }; };
  await assert.rejects(
    readProjectInfo(dir, { exec }),
    (error) => error instanceof ToolchainError && /unresolved conflicts/.test(error.message),
  );
  assert.strictEqual(called, false);
});

test('makefile_without_conflict_markers_goes_on_to_make', async () => {
  const dir = tmp();
  fs.writeFileSync(path.join(dir, 'Makefile'), 'A=1\n# <<<<<<<no space\n');
  assert.deepStrictEqual(await readProjectInfo(dir, { exec: async () => ({ stdout: '{"a":1}' }) }), { a: 1 });
});

test('makefile_conflict_helper', () => {
  const dir = tmp();
  assert.strictEqual(makefileConflictError(dir), null); // missing Makefile
  fs.writeFileSync(path.join(dir, 'Makefile'), 'A=1\n');
  assert.strictEqual(makefileConflictError(dir), null);
  fs.writeFileSync(path.join(dir, 'Makefile'), 'A=1\n<<<<<<< Makefile\nB=2\n');
  const error = makefileConflictError(dir);
  assert.ok(error instanceof ToolchainError);
  assert.match(error.message, /unresolved conflicts/);
});

test('missing_makefile_falls_through_to_make', async () => {
  await assert.rejects(
    readProjectInfo(tmp(), { exec: rejecting('make: *** No targets specified and no makefile found.  Stop.') }),
    (error) => error instanceof ToolchainError && /No Makefile/.test(error.message),
  );
});

test('no_makefile_message', async () => {
  await assert.rejects(
    readProjectInfo('/p', { exec: rejecting('make: *** No targets specified and no makefile found.  Stop.') }),
    (error) => error instanceof ToolchainError && /No Makefile/.test(error.message),
  );
});

test('other_make_failure_is_reported', async () => {
  await assert.rejects(
    readProjectInfo('/p', { exec: rejecting('Makefile:181: *** boom.  Stop.') }),
    (error) => error instanceof ToolchainError && /boom/.test(error.message),
  );
});

const GOOD = {
  'stm8-gdb': { stdout: 'GNU gdb (GDB) 15.0.50.20240111-git\n' },
  openocd: { stdout: '', stderr: 'Open On-Chip Debugger 0.12.0\n' },
  lsusb: { stdout: 'Bus 003 Device 072: ID 0483:374b STMicroelectronics ST-LINK/V2.1\n' },
};

function fakeExec(overrides = {}) {
  const table = { ...GOOD, ...overrides };
  return async (cmd) => {
    const entry = table[cmd];
    if (entry === null) throw Object.assign(new Error('not found'), { code: 'ENOENT' });
    return entry;
  };
}

async function problems({ exec = {}, session, elf = true } = {}) {
  const cwd = tmp();
  const elfPath = path.join(cwd, 'out.elf');
  if (elf) fs.writeFileSync(elfPath, '');
  if (session !== undefined) fs.writeFileSync(path.join(cwd, '.debug-session'), `${session}\n`);
  return preflight({ elf: elfPath }, cwd, { exec: fakeExec(exec) });
}

test('preflight_all_good', async () => {
  assert.deepStrictEqual(await problems(), []);
});

test('preflight_old_gdb', async () => {
  const found = await problems({ exec: { 'stm8-gdb': { stdout: 'GNU gdb (GDB) 14.2\n' } } });
  assert.strictEqual(found.length, 1);
  assert.match(found[0], /stm8-gdb 15 or newer/);
});

test('preflight_missing_gdb_and_openocd', async () => {
  const found = await problems({ exec: { 'stm8-gdb': null, openocd: null } });
  assert.deepStrictEqual(found, ['stm8-gdb not found in PATH', 'openocd not found in PATH']);
});

test('preflight_no_stlink', async () => {
  const found = await problems({ exec: { lsusb: { stdout: 'Bus 001 Device 002: ID 8087:0024 Intel Corp.\n' } } });
  assert.match(found[0], /No ST-Link/);
});

test('preflight_without_lsusb_skips_usb_check', async () => {
  assert.deepStrictEqual(await problems({ exec: { lsusb: null } }), []);
});

test('preflight_live_debug_session', async () => {
  const found = await problems({ session: process.pid });
  assert.strictEqual(found.length, 1);
  assert.match(found[0], new RegExp(`make debug is running \\(PID ${process.pid}\\)`));
});

test('preflight_dead_debug_session_is_ignored', async () => {
  assert.deepStrictEqual(await problems({ session: 2147483646 }), []);
});

test('preflight_missing_elf', async () => {
  const found = await problems({ elf: false });
  assert.match(found[0], /out\.elf not found\. Build failed\?/);
});

test('version_notice', () => {
  const dir = tmp();
  fs.mkdirSync(path.join(dir, '.make', 'vscode'), { recursive: true });
  fs.writeFileSync(path.join(dir, '.make', 'vscode', 'package.json'), JSON.stringify({ version: '0.2.0' }));
  assert.match(versionNotice('0.1.0', dir), /newer.*0\.2\.0.*0\.1\.0.*Update the extension.*make vscode/);
  assert.strictEqual(versionNotice('0.2.0', dir), null);
  assert.strictEqual(versionNotice('0.10.0', dir), null);
  assert.strictEqual(versionNotice('0.1.0', tmp()), null); // no extension sources in the project
});

test('upgrade_offer_four_cases', () => {
  const project = (makefileSdcc, version) => {
    const dir = tmp();
    fs.mkdirSync(path.join(dir, '.make', 'vscode'), { recursive: true });
    if (makefileSdcc) fs.writeFileSync(path.join(dir, '.make', 'Makefile-sdcc'), '');
    if (version) fs.writeFileSync(path.join(dir, '.make', 'vscode', 'package.json'), JSON.stringify({ version }));
    return dir;
  };
  assert.strictEqual(upgradeOffer('0.2.0', project(false, '0.1.0')), false); // not a toolchain project
  assert.strictEqual(upgradeOffer('0.2.0', project(true, null)), true); // no extension sources yet
  assert.strictEqual(upgradeOffer('0.2.0', project(true, '0.1.0')), true); // older
  assert.strictEqual(upgradeOffer('0.2.0', project(true, '0.2.0')), false); // same
  assert.strictEqual(upgradeOffer('0.2.0', project(true, '0.10.0')), false); // numeric, not textual
  assert.strictEqual(upgradeOffer('0.2.0', tmp()), false); // no .make at all
});

test('upgrade_offer_unparseable_package_json', () => {
  const dir = tmp();
  fs.mkdirSync(path.join(dir, '.make', 'vscode'), { recursive: true });
  fs.writeFileSync(path.join(dir, '.make', 'Makefile-sdcc'), '');
  fs.writeFileSync(path.join(dir, '.make', 'vscode', 'package.json'), '{broken');
  assert.strictEqual(upgradeOffer('0.2.0', dir), true);
});

// --- Task 10: offline SFR model -----------------------------------------------------------

const { loadSfrModel } = require('../src/project');

test('load_sfr_model_runs_sfr_json_offline', async () => {
  const model = { running: false, periphs: [{ name: 'UART1', base: 1, other: [], regs: [{ name: 'DR', sideEffect: true }] }] };
  let call;
  const exec = async (cmd, args, options) => {
    call = { cmd, args, options };
    return { stdout: `${JSON.stringify(model)}\n` };
  };
  const parsed = await loadSfrModel({ sfr: '/p/sfr.elf' }, '/p', { exec });
  assert.deepStrictEqual(parsed.sideEffects, { UART1: ['DR'] });
  assert.strictEqual(call.cmd, 'stm8-gdb');
  assert.ok(call.args.includes('-batch'));
  assert.ok(call.args.includes('sfr-json'));
  assert.strictEqual(call.options.env.STM8_SFR, '/p/sfr.elf');
  assert.strictEqual(call.options.cwd, '/p');
});

test('load_sfr_model_failure_is_a_toolchain_error', async () => {
  const exec = async () => {
    throw Object.assign(new Error('x'), { stderr: 'Peripheral registers are not loaded.' });
  };
  await assert.rejects(loadSfrModel({ sfr: '/p/sfr.elf' }, '/p', { exec }), (e) => e instanceof ToolchainError && /not loaded/.test(e.message));
});

// --- Task 12: chip list and switch --------------------------------------------------------

const { listChips, switchChip } = require('../src/project');

test('list_chips_runs_devices_py', async () => {
  const devices = { 'Access line': { STM8S103F3: 'stm8s103f2' } };
  let call;
  const exec = async (cmd, args, options) => {
    call = { cmd, args, options };
    return { stdout: JSON.stringify(devices) };
  };
  assert.deepStrictEqual(await listChips('/p', { exec }), devices);
  assert.deepStrictEqual(call.args, ['.make/devices.py']);
  assert.strictEqual(call.options.cwd, '/p');
});

test('switch_chip_calls_make_without_questions', async () => {
  let call;
  await switchChip('/p', 'stm8s103f3', { exec: async (cmd, args, options) => { call = { cmd, args, options }; return { stdout: '' }; } });
  assert.strictEqual(call.cmd, 'make');
  assert.deepStrictEqual(call.args, ['-s', '--no-print-directory', 'switch-device', 'CHIP=stm8s103f3']);
  assert.strictEqual(call.options.env.LC_ALL, 'C');
});

test('switch_chip_failure_carries_the_reason', async () => {
  await assert.rejects(
    switchChip('/p', 'stm8s001j3', { exec: rejecting('SPL has no support for STM8S001') }),
    (error) => error instanceof ToolchainError && /Cannot switch to stm8s001j3: SPL has no support for STM8S001/.test(error.message),
  );
});
