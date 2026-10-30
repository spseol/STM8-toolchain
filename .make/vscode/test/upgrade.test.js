'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { runUpgrade } = require('../src/upgrade');

const URL = 'https://example.org/toolchain.git';
const failure = (code, stdout = '', stderr = '') => Object.assign(new Error(`exit ${code}`), { code, stdout, stderr });

/** Fake exec: records the calls; `python` decides the result of the python3 step. */
function fakeExec({ fetch, show, python } = {}) {
  const calls = [];
  const exec = async (cmd, args, options) => {
    calls.push({ cmd, args, options });
    if (cmd === 'git' && args[0] === 'fetch') return fetch ? fetch() : { stdout: '', stderr: '' };
    if (cmd === 'git' && args[0] === 'show') return show ? show() : { stdout: 'SOURCE-OF-UPGRADE', stderr: '' };
    if (cmd === 'python3') return python ? python() : { stdout: '', stderr: '' };
    throw new Error(`unexpected ${cmd}`);
  };
  return { exec, calls };
}

const REPORT = JSON.stringify({ replaced: 3, removed: 1, makefile: 'merged', launch: 'created', backup: '', gitignore_added: [], notes: [] });

test('pipeline_fetch_show_python_in_order', async () => {
  const { exec, calls } = fakeExec({ python: () => ({ stdout: `Updated .make/\n${REPORT}\n` }) });
  const result = await runUpgrade('/p', { url: URL, exec });
  assert.deepStrictEqual(calls.map((c) => [c.cmd, ...c.args.slice(0, 1)]), [['git', 'fetch'], ['git', 'show'], ['python3', '-c']]);
  assert.deepStrictEqual(calls[0].args, ['fetch', '--', URL, 'main']);
  assert.deepStrictEqual(calls[1].args, ['show', 'FETCH_HEAD:.make/upgrade.py']);
  assert.deepStrictEqual(calls[2].args, ['-c', 'SOURCE-OF-UPGRADE', 'FETCH_HEAD', '--json']);
  for (const call of calls) {
    assert.strictEqual(call.options.cwd, '/p');
    assert.ok(call.options.maxBuffer >= 16 * 1024 * 1024);
  }
  assert.strictEqual(result.code, 0);
});

test('code_0_output_is_the_summary_without_the_json_line', async () => {
  const { exec } = fakeExec({ python: () => ({ stdout: `Updated .make/: 3 files replaced.\nMakefile: merged.\n${REPORT}\n` }) });
  const result = await runUpgrade('/p', { url: URL, exec });
  assert.deepStrictEqual(result, { code: 0, output: 'Updated .make/: 3 files replaced.\nMakefile: merged.' });
});

test('code_2_is_returned_with_the_summary', async () => {
  const conflict = JSON.stringify({ makefile: 'conflict' });
  const { exec } = fakeExec({ python: () => { throw failure(2, `Makefile: conflict.\n${conflict}\n`); } });
  assert.deepStrictEqual(await runUpgrade('/p', { url: URL, exec }), { code: 2, output: 'Makefile: conflict.' });
});

test('code_1_output_is_the_trimmed_stderr', async () => {
  const { exec } = fakeExec({ python: () => { throw failure(1, '', 'The project has uncommitted changes.\n'); } });
  assert.deepStrictEqual(await runUpgrade('/p', { url: URL, exec }), { code: 1, output: 'The project has uncommitted changes.' });
});

test('code_3_parses_needs_switch', async () => {
  const { exec } = fakeExec({ python: () => { throw failure(3, '{"needsSwitch": "sdcc-gas"}\n'); } });
  assert.deepStrictEqual(await runUpgrade('/p', { url: URL, exec }), { code: 3, output: '', needsSwitch: 'sdcc-gas' });
});

test('switch_choice_is_passed_on', async () => {
  const { exec, calls } = fakeExec({ python: () => ({ stdout: `ok\n${REPORT}\n` }) });
  await runUpgrade('/p', { url: URL, switchChoice: 'yes', exec });
  assert.deepStrictEqual(calls[2].args, ['-c', 'SOURCE-OF-UPGRADE', 'FETCH_HEAD', '--json', '--switch', 'yes']);
  await runUpgrade('/p', { url: URL, switchChoice: 'no', exec });
  assert.deepStrictEqual(calls[5].args.slice(-2), ['--switch', 'no']);
});

test('fetch_failure_is_code_1_and_stops', async () => {
  const { exec, calls } = fakeExec({ fetch: () => { throw failure(128, '', 'fatal: unable to access\n'); } });
  const result = await runUpgrade('/p', { url: URL, exec });
  assert.deepStrictEqual(result, { code: 1, output: `Cannot download the toolchain from ${URL}: fatal: unable to access` });
  assert.strictEqual(calls.length, 1);
});

test('show_failure_means_toolchain_without_upgrade_script', async () => {
  const { exec, calls } = fakeExec({ show: () => { throw failure(128, '', 'fatal: path does not exist\n'); } });
  const result = await runUpgrade('/p', { url: URL, exec });
  assert.deepStrictEqual(result, { code: 1, output: `The toolchain at ${URL} has no .make/upgrade.py, nothing was changed.` });
  assert.strictEqual(calls.length, 2);
});

test('missing_python_is_code_1', async () => {
  const { exec } = fakeExec({ python: () => { throw Object.assign(new Error('spawn python3 ENOENT'), { code: 'ENOENT' }); } });
  const result = await runUpgrade('/p', { url: URL, exec });
  assert.strictEqual(result.code, 1);
  assert.match(result.output, /python3/);
});

test('url_that_looks_like_an_option_stays_after_double_dash', async () => {
  const { exec, calls } = fakeExec();
  await runUpgrade('/p', { url: '--upload-pack=touch /tmp/x', exec });
  assert.deepStrictEqual(calls[0].args, ['fetch', '--', '--upload-pack=touch /tmp/x', 'main']);
});
