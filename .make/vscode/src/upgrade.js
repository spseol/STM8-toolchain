'use strict';
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');

const run = promisify(execFile);
const MAX_BUFFER = 16 * 1024 * 1024; // the script source is ~15 kB, the summary is short

const message = (error) => `${error.stderr || ''}`.trim() || `${error.message || error}`.trim();

/**
 * Updates the project in ROOT to the toolchain at URL: fetches it, then runs its own
 * .make/upgrade.py (so the newest logic always applies). Never throws for a failed upgrade:
 * the result is { code, output, needsSwitch? } with the exit code of upgrade.py
 * (0 done, 1 refused, 2 done with conflicts in Makefile, 3 asks whether to switch the Makefile variant).
 */
async function runUpgrade(root, { url, switchChoice, exec = run } = {}) {
  const options = { cwd: root, maxBuffer: MAX_BUFFER, env: { ...process.env, GIT_TERMINAL_PROMPT: '0' } };
  try {
    await exec('git', ['fetch', url, 'main'], options);
  } catch (error) {
    return { code: 1, output: `Cannot download the toolchain from ${url}: ${message(error)}` };
  }
  let source;
  try {
    ({ stdout: source } = await exec('git', ['show', 'FETCH_HEAD:.make/upgrade.py'], options));
  } catch {
    return { code: 1, output: `The toolchain at ${url} has no .make/upgrade.py, nothing was changed.` };
  }

  const args = ['-c', source, 'FETCH_HEAD', '--json', ...(switchChoice ? ['--switch', switchChoice] : [])];
  let code = 0;
  let stdout;
  let stderr = '';
  try {
    ({ stdout } = await exec('python3', args, options));
  } catch (error) {
    if (typeof error.code !== 'number') return { code: 1, output: `Cannot run python3: ${message(error)}` };
    ({ code } = error);
    stdout = error.stdout || '';
    stderr = error.stderr || '';
  }

  const lines = String(stdout).trimEnd().split('\n');
  if (code === 3) {
    try {
      return { code, output: '', needsSwitch: JSON.parse(lines[lines.length - 1]).needsSwitch };
    } catch {
      return { code: 1, output: `Unexpected answer of the upgrade script: ${String(stdout).trim().slice(0, 200)}` };
    }
  }
  if (code === 1) return { code, output: stderr.trim() };
  lines.pop(); // the last line is the report as JSON; the lines before it are for the student
  return { code, output: lines.join('\n').trim() };
}

module.exports = { runUpgrade };
