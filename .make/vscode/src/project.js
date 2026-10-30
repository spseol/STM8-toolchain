'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { execFile, spawn } = require('node:child_process');
const { promisify } = require('node:util');

const { parse } = require('./sfrmodel');

const run = promisify(execFile);

/** A problem the student can fix; its message is shown as it is. */
class ToolchainError extends Error {
  /** `fix`: name of the command that repairs the problem (the error dialog offers it as a button). */
  constructor(message, { fix } = {}) {
    super(message);
    if (fix) this.fix = fix;
  }
}

/** The error for a Makefile with unresolved conflict markers (after Update Toolchain), else null. */
function makefileConflictError(cwd) {
  let makefile;
  try {
    makefile = fs.readFileSync(path.join(cwd, 'Makefile'), 'utf8');
  } catch {
    return null; // no Makefile: make says so
  }
  return /^<{7} /m.test(makefile)
    ? new ToolchainError('Makefile has unresolved conflicts from Update Toolchain – resolve them (Accept Current/Incoming) and save')
    : null;
}

/** Paths and the OpenOCD command of the project in CWD (`make dap-info`). */
async function readProjectInfo(cwd, { exec = run } = {}) {
  const conflict = makefileConflictError(cwd);
  if (conflict) throw conflict;
  let stdout;
  try {
    ({ stdout } = await exec('make', ['-s', '--no-print-directory', 'dap-info'], {
      cwd,
      env: { ...process.env, LC_ALL: 'C' }, // make's messages are matched in English
    }));
  } catch (error) {
    const text = `${error.stderr || ''}${error.message || ''}`;
    if (/No rule to make target/.test(text)) {
      throw new ToolchainError(
        'Old toolchain – run STM8: Update Toolchain (or update .make/ by hand and add the line -include .make/vscode.mk to Makefile)',
        { fix: 'updateToolchain' },
      );
    }
    if (/no makefile found/i.test(text)) {
      throw new ToolchainError(`No Makefile in ${cwd} – open the STM8 project folder`);
    }
    throw new ToolchainError(`make dap-info failed: ${(error.stderr || error.message).trim()}`);
  }
  try {
    return JSON.parse(stdout);
  } catch {
    throw new ToolchainError(`Unexpected output of make dap-info: ${stdout.trim().slice(0, 200)}`);
  }
}

/** Why F5 cannot work (empty list = it can). Names what to fix, not stack traces. */
async function preflight(info, cwd, { exec = run } = {}) {
  const problems = [];
  const tryExec = async (cmd, args = []) => {
    try {
      return await exec(cmd, args);
    } catch {
      return null;
    }
  };

  const gdb = await tryExec('stm8-gdb', ['--version']);
  if (!gdb) {
    problems.push('stm8-gdb not found in PATH');
  } else {
    const major = /GNU gdb[^\n]*?(\d+)\.\d+/.exec(gdb.stdout);
    if (!major || Number(major[1]) < 15) {
      problems.push(`stm8-gdb 15 or newer is required (found ${major ? major[1] : 'unknown version'})`);
    }
  }
  if (!(await tryExec('openocd', ['--version']))) problems.push('openocd not found in PATH');

  const usb = await tryExec('lsusb'); // no lsusb: cannot tell, let OpenOCD say
  if (usb && !/ID 0483:/i.test(usb.stdout)) problems.push('No ST-Link found on USB. Is the board connected?');

  try {
    const pid = Number.parseInt(fs.readFileSync(path.join(cwd, '.debug-session'), 'utf8'), 10);
    process.kill(pid, 0); // throws when the process is gone
    problems.push(`make debug is running (PID ${pid}); close it first.`);
  } catch (error) {
    if (error.code === 'EPERM') problems.push('make debug is running; close it first.');
  }

  if (!fs.existsSync(info.elf)) problems.push(`${info.elf} not found. Build failed? Run Build.`);
  return problems;
}

/** Version of the extension sources in the project (`.make/vscode/package.json`), or null when missing or broken. */
function projectExtensionVersion(projectDir) {
  try {
    const { version } = JSON.parse(fs.readFileSync(path.join(projectDir, '.make', 'vscode', 'package.json'), 'utf8'));
    return typeof version === 'string' ? version : null;
  } catch {
    return null;
  }
}

/** Numeric comparison of dotted versions: > 0 when A is newer than B, < 0 when older, 0 when equal. */
function compareVersions(a, b) {
  const parts = (version) => version.split('.').map(Number);
  const [x, y] = [parts(a), parts(b)];
  for (let i = 0; i < 3; i++) {
    if (x[i] !== y[i]) return x[i] - y[i];
  }
  return 0;
}

/** Text for the student when the project carries a newer extension than the installed one, else null. */
function versionNotice(installed, projectDir) {
  const available = projectExtensionVersion(projectDir);
  if (available === null || compareVersions(available, installed) <= 0) return null;
  return `This project has a newer STM8 extension (${available}) than the installed one (${installed}). `
    + 'Update the extension (Extensions view) or run "make vscode", then restart the editor.';
}

/** Is this a toolchain project whose .make/ is older than the installed extension (Update Toolchain helps)? */
function upgradeOffer(installed, projectDir) {
  if (!projectDir) return false;
  if (!fs.existsSync(path.join(projectDir, '.make', 'Makefile-sdcc'))) return false;
  const available = projectExtensionVersion(projectDir);
  return available === null || compareVersions(available, installed) < 0;
}

/** Peripherals, registers and bits of the chip, read offline (no chip, no session needed). */
async function loadSfrModel(info, cwd, { exec = run } = {}) {
  try {
    const { stdout } = await exec(
      'stm8-gdb',
      ['-q', '-batch', '-ex', 'source .make/stm8gdb.py', '-ex', 'source .make/stm8sfr.py', '-ex', 'sfr-json'],
      { cwd, env: { ...process.env, STM8_SFR: info.sfr }, maxBuffer: 64 * 1024 * 1024 },
    );
    return parse(stdout);
  } catch (error) {
    throw new ToolchainError(`Cannot load the peripheral registers: ${(error.stderr || error.message).trim().slice(0, 300)}`);
  }
}

/** Chips the toolchain can build: { family: { CHIP: datasheet } } (`.make/devices.py`). */
async function listChips(cwd, { exec = run } = {}) {
  const { stdout } = await exec('python3', ['.make/devices.py'], { cwd });
  return JSON.parse(stdout);
}

/** Writes CHIP (e.g. stm8s103f3) into the Makefile and cleans the old build (`make switch-device`). */
async function switchChip(cwd, chip, { exec = run } = {}) {
  try {
    await exec('make', ['-s', '--no-print-directory', 'switch-device', `CHIP=${chip}`], {
      cwd,
      env: { ...process.env, LC_ALL: 'C' },
    });
  } catch (error) {
    throw new ToolchainError(`Cannot switch to ${chip}: ${(error.stderr || error.message).trim()}`);
  }
}

/** The last N lines of the OpenOCD log that contain "Error". */
function openocdTail(logPath, n = 5) {
  try {
    return fs.readFileSync(logPath, 'utf8').split('\n').filter((line) => line.includes('Error')).slice(-n);
  } catch {
    return [];
  }
}

/** Is an OpenOCD process running? It may hold the ST-Link. */
async function otherOpenocd({ exec = run } = {}) {
  try {
    await exec('pgrep', ['-x', 'openocd']);
    return true;
  } catch {
    return false;
  }
}

/** stm8-gdb as DAP server, with the environment `make debug` gives it. */
function spawnGdb(info, cwd) {
  return spawn('stm8-gdb', ['-q', '-i', 'dap', '-x', '.make/gdbinit'], {
    cwd,
    env: {
      ...process.env,
      STM8_UI: 'dap',
      STM8_OPENOCD: info.openocd,
      STM8_OPENOCD_LOG: info.openocdLog,
      STM8_SFR: info.sfr,
    },
  });
}

module.exports = {
  ToolchainError, makefileConflictError, readProjectInfo, preflight, versionNotice, upgradeOffer, loadSfrModel, listChips, switchChip, openocdTail, otherOpenocd, spawnGdb,
};
