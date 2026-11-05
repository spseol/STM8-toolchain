'use strict';
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');

const { PYTHON } = require('./platform');

const run = promisify(execFile);
const MAX_BUFFER = 16 * 1024 * 1024; // the script source is ~15 kB, the summary is short

const message = (error) => `${error.stderr || ''}`.trim() || `${error.message || error}`.trim();

/**
 * Updates the project in ROOT to the toolchain at URL: fetches it, then runs its own
 * .make/upgrade.py (so the newest logic always applies). Never throws for a failed upgrade:
 * the result is { code, output, needsSwitch?, conflict? } with the exit code of upgrade.py
 * (0 done, 1 refused, 2 done with conflicts in Makefile, 3 asks whether to switch the Makefile variant).
 * Code 2 counts as a conflict (conflict: true) only with the JSON report saying so: Python and
 * argparse exit with 2 on usage errors, which is then a failure (code 1).
 */
async function runUpgrade(root, { url, switchChoice, exec = run } = {}) {
  const options = { cwd: root, maxBuffer: MAX_BUFFER, env: { ...process.env, GIT_TERMINAL_PROMPT: '0' } };
  try {
    // `--`: a url that starts with - is then a repository, never an option
    await exec('git', ['fetch', '--', url, 'main'], options);
  } catch (error) {
    return { code: 1, output: `Cannot download the toolchain from ${url}: ${message(error)}` };
  }
  let source;
  try {
    ({ stdout: source } = await exec('git', ['show', 'FETCH_HEAD:.make/upgrade.py'], options));
  } catch {
    return { code: 1, output: `The toolchain at ${url} has no .make/upgrade.py, nothing was changed.` };
  }

  // -I: the cwd is the project, whose difflib.py or json.py must not replace the standard library
  const args = ['-I', '-c', source, 'FETCH_HEAD', '--json', ...(switchChoice ? ['--switch', switchChoice] : [])];
  let code = 0;
  let stdout;
  let stderr = '';
  try {
    ({ stdout } = await exec(PYTHON, args, options));
  } catch (error) {
    if (typeof error.code !== 'number') return { code: 1, output: `Cannot run ${PYTHON}: ${message(error)}` };
    ({ code } = error);
    stdout = error.stdout || '';
    stderr = error.stderr || '';
  }

  // upgrade.py ends only with 0, 1, 2 or 3; anything else is the interpreter or the shell (Windows: 9009 = the
  // Microsoft Store stub of python.exe or python3.exe, "command not found")
  if (![0, 1, 2, 3].includes(code)) {
    const detail = stderr.trim() || String(stdout).trim();
    return { code: 1, output: `Update Toolchain failed: ${PYTHON} exited with code ${code}${detail ? `: ${detail}` : ''}` };
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
  let report = null;
  try {
    report = JSON.parse(lines[lines.length - 1]);
  } catch {
    // not a report
  }
  if (code === 2 && !(report && report.makefile === 'conflict')) {
    return { code: 1, output: stderr.trim() || String(stdout).trim() || 'Update Toolchain failed (code 2).' };
  }
  lines.pop(); // the last line is the report as JSON; the lines before it are for the student
  const output = lines.join('\n').trim();
  return code === 2 ? { code, output, conflict: true } : { code, output };
}

module.exports = { runUpgrade };
