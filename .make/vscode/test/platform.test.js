'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { PYTHON, GDB_PYTHON_ENV, pathKey, gitUsrBin, toolEnv, taskEnv, applyTerminalEnv } = require('../src/platform');

test('gdb_python_runs_in_utf8_mode_only_on_windows', () => {
  assert.deepStrictEqual(GDB_PYTHON_ENV, process.platform === 'win32' ? { PYTHONUTF8: '1' } : {});
});

const GIT = 'C:\\Program Files\\Git';
const BASH = `${GIT}\\usr\\bin\\bash.exe`;
const win = (files) => ({ platform: 'win32', exists: (file) => files.includes(file) });

test('python_is_python3_except_on_windows', () => {
  assert.strictEqual(PYTHON, process.platform === 'win32' ? 'python' : 'python3');
});

test('path_key_keeps_the_case_of_the_environment', () => {
  assert.strictEqual(pathKey({ Path: 'a' }), 'Path');
  assert.strictEqual(pathKey({ PATH: 'a' }), 'PATH');
  assert.strictEqual(pathKey({}), 'PATH');
});

test('git_usr_bin_is_found_next_to_git_exe_in_path', () => {
  const env = { Path: `C:\\Windows;${GIT}\\cmd` };
  assert.strictEqual(gitUsrBin(env, win([`${GIT}\\cmd\\git.exe`, BASH])), `${GIT}\\usr\\bin`);
});

test('git_usr_bin_falls_back_to_program_files', () => {
  const env = { Path: 'C:\\Windows', ProgramFiles: 'C:\\Program Files' };
  assert.strictEqual(gitUsrBin(env, win([BASH])), `${GIT}\\usr\\bin`);
});

test('git_usr_bin_is_null_without_git_or_off_windows', () => {
  assert.strictEqual(gitUsrBin({ Path: 'C:\\Windows' }, win([])), null);
  assert.strictEqual(gitUsrBin({ PATH: '/usr/bin' }, { platform: 'linux', exists: () => true }), null);
});

test('tool_env_puts_git_usr_bin_first_and_keeps_the_rest', () => {
  const env = { Path: `C:\\Windows;${GIT}\\cmd`, LANG: 'cs' };
  const result = toolEnv(env, win([`${GIT}\\cmd\\git.exe`, BASH]));
  assert.strictEqual(result.Path, `${GIT}\\usr\\bin;C:\\Windows;${GIT}\\cmd`);
  assert.strictEqual(result.LANG, 'cs');
  assert.strictEqual(env.Path, `C:\\Windows;${GIT}\\cmd`, 'the original is not changed');
  assert.strictEqual('PATH' in result, false, 'no second spelling of PATH');
});

test('tool_env_does_not_add_it_twice', () => {
  const env = { Path: `${GIT}\\usr\\bin;C:\\Windows` };
  assert.strictEqual(toolEnv(env, win([BASH])).Path, env.Path);
});

test('tool_env_is_a_plain_copy_on_linux_and_macos', () => {
  const env = { PATH: '/usr/bin:/bin', HOME: '/home/a' };
  const result = toolEnv(env, { platform: 'linux', exists: () => true });
  assert.deepStrictEqual(result, env);
  assert.notStrictEqual(result, env);
});

test('task_env_has_only_the_path_and_only_when_it_changes', () => {
  const env = { Path: `C:\\Windows;${GIT}\\cmd` };
  assert.deepStrictEqual(taskEnv(env, win([`${GIT}\\cmd\\git.exe`, BASH])), { Path: `${GIT}\\usr\\bin;C:\\Windows;${GIT}\\cmd` });
  assert.deepStrictEqual(taskEnv({ PATH: '/usr/bin' }, { platform: 'linux', exists: () => true }), {});
  assert.deepStrictEqual(taskEnv({ Path: 'C:\\Windows' }, win([])), {});
});

const collection = () => {
  const calls = [];
  return { calls, prepend: (name, value) => calls.push([name, value]) };
};

test('terminal_env_prepends_git_usr_bin_to_the_path_of_new_terminals', () => {
  const env = { Path: `C:\\Windows;${GIT}\\cmd` };
  const c = collection();
  assert.strictEqual(applyTerminalEnv(c, env, win([`${GIT}\\cmd\\git.exe`, BASH])), true);
  assert.deepStrictEqual(c.calls, [['Path', `${GIT}\\usr\\bin;`]]);
});

test('terminal_env_adds_nothing_when_not_needed', () => {
  const c = collection();
  assert.strictEqual(applyTerminalEnv(c, { Path: `${GIT}\\usr\\bin;C:\\Windows` }, win([BASH])), false, 'already in PATH');
  assert.strictEqual(applyTerminalEnv(c, { Path: 'C:\\Windows' }, win([])), false, 'no Git');
  assert.strictEqual(applyTerminalEnv(c, { PATH: '/usr/bin' }, { platform: 'linux', exists: () => true }), false, 'not Windows');
  assert.strictEqual(applyTerminalEnv(undefined, { Path: 'C:\\Windows' }, win([BASH])), false, 'no collection');
  assert.deepStrictEqual(c.calls, []);
});
