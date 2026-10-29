'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { execFile, spawn } = require('node:child_process');
const { promisify } = require('node:util');

const { parse } = require('./sfrmodel');

const run = promisify(execFile);

/** A problem the student can fix; its message is shown as it is. */
class ToolchainError extends Error {}

/** Paths and the OpenOCD command of the project in CWD (`make dap-info`). */
async function readProjectInfo(cwd, { exec = run } = {}) {
  let stdout;
  try {
    ({ stdout } = await exec('make', ['-s', '--no-print-directory', 'dap-info'], {
      cwd,
      env: { ...process.env, LC_ALL: 'C' }, // make's messages are matched in English
    }));
  } catch (error) {
    const text = `${error.stderr || ''}${error.message || ''}`;
    if (/No rule to make target/.test(text)) {
      throw new ToolchainError('Old toolchain – update .make/ and add the line -include .make/vscode.mk to Makefile');
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

/** Text for the student when the project carries a newer extension than the installed one, else null. */
function versionNotice(installed, projectDir) {
  let available;
  try {
    available = JSON.parse(fs.readFileSync(path.join(projectDir, '.make', 'vscode', 'package.json'), 'utf8')).version;
  } catch {
    return null;
  }
  const parts = (version) => version.split('.').map(Number);
  const [a, b] = [parts(available), parts(installed)];
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) {
      return a[i] > b[i]
        ? `This project has a newer STM8 extension (${available}) than the installed one (${installed}). `
          + 'Run "make vscode" and restart the editor.'
        : null;
    }
  }
  return null;
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
  ToolchainError, readProjectInfo, preflight, versionNotice, loadSfrModel, listChips, switchChip, openocdTail, otherOpenocd, spawnGdb,
};
