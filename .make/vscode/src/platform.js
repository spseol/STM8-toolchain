'use strict';
const fs = require('node:fs');
const path = require('node:path');

/**
 * Python of the toolchain, the same choice as PYTHON in the Makefile. Windows has no `python3`: the
 * python3.exe in %LOCALAPPDATA%\Microsoft\WindowsApps is only a stub for the Microsoft Store,
 * which exits with 9009 ("Update Toolchain failed (code 9009)"), so it is `python` there.
 * Elsewhere the first of `python3` and `python` found in PATH (macOS has only python3, Linux usually both);
 * `python3` when neither is found, so the error message names the usual command.
 */
function detectPython(env = process.env, { platform = process.platform, exists = isExecutable } = {}) {
  if (platform === 'win32') return 'python';
  const dirs = String(env[pathKey(env)] || '').split(path.delimiter).filter(Boolean);
  for (const name of ['python3', 'python']) {
    if (dirs.some((dir) => exists(path.join(dir, name)))) return name;
  }
  return 'python3';
}

function isExecutable(file) {
  try {
    fs.accessSync(file, fs.constants.X_OK);
    return fs.statSync(file).isFile();
  } catch {
    return false;
  }
}

const PYTHON = detectPython();

/**
 * Environment of the Python inside stm8-gdb. Windows: its default text encoding is the ANSI code page (cp1250), but the
 * text of the scripts is UTF-8, so the Debug Console showed "periferiĂ­" instead of "periferií". UTF-8 mode fixes it.
 * Linux and macOS use UTF-8 already, so nothing is added there.
 */
const GDB_PYTHON_ENV = process.platform === 'win32' ? { PYTHONUTF8: '1' } : {};

/** Name of the PATH variable in ENV: on Windows it is usually `Path`, and a copy of process.env is case sensitive. */
function pathKey(env) {
  return Object.keys(env).find((key) => key.toUpperCase() === 'PATH') || 'PATH';
}

/**
 * Windows: the directory with bash, nproc, ls, ... of Git for Windows (`<Git>\usr\bin`), or null. The Makefile
 * needs them; an editor started from the Start menu has only `<Git>\cmd` in PATH (Git Bash adds usr\bin
 * to PATH itself, so `make` works there and fails in VSCodium).
 */
function gitUsrBin(env = process.env, { exists = fs.existsSync, platform = process.platform } = {}) {
  if (platform !== 'win32') return null;
  const dirs = String(env[pathKey(env)] || '').split(';').filter(Boolean);
  const roots = [];
  for (const dir of dirs) {
    if (exists(path.win32.join(dir, 'git.exe'))) roots.push(path.win32.dirname(dir)); // <Git>\cmd or <Git>\bin
  }
  for (const base of [env.ProgramFiles, env.LOCALAPPDATA && path.win32.join(env.LOCALAPPDATA, 'Programs'), env.ProgramW6432]) {
    if (base) roots.push(path.win32.join(base, 'Git'));
  }
  for (const root of roots) {
    const usrBin = path.win32.join(root, 'usr', 'bin');
    if (exists(path.win32.join(usrBin, 'bash.exe'))) return usrBin;
  }
  return null;
}

/**
 * ENV (default process.env) for running make: on Windows with `<Git>\usr\bin` first in PATH, so that make
 * finds bash. Elsewhere, and when Git is not found, it is a plain copy of ENV.
 */
function toolEnv(env = process.env, options = {}) {
  const result = { ...env };
  const usrBin = gitUsrBin(env, options);
  if (!usrBin) return result;
  const key = pathKey(result);
  const current = String(result[key] || '');
  if (current.split(';').some((dir) => dir.toLowerCase() === usrBin.toLowerCase())) return result;
  result[key] = `${usrBin};${current}`;
  return result;
}

/**
 * `env` for the options of a ShellExecution (VS Code adds it to the environment of the editor): only PATH, only when
 * toolEnv() changes it, else an empty object, so the options stay as they were on Linux and macOS.
 */
function taskEnv(env = process.env, options = {}) {
  const key = pathKey(env);
  const changed = toolEnv(env, options);
  return changed[key] === env[key] ? {} : { [key]: changed[key] };
}

/**
 * Terminal of the editor (the PowerShell in VSCodium): `make` typed there must find bash too, and the editor started from
 * the Start menu does not have `<Git>\usr\bin` in PATH. COLLECTION is `context.environmentVariableCollection`; its
 * changes reach terminals opened afterwards. Returns true when it added something (not on Linux and macOS, not when
 * Git is missing or its usr\bin is already in PATH).
 */
function applyTerminalEnv(collection, env = process.env, options = {}) {
  const usrBin = gitUsrBin(env, options);
  if (!usrBin || !collection) return false;
  const key = pathKey(env);
  if (String(env[key] || '').split(';').some((dir) => dir.toLowerCase() === usrBin.toLowerCase())) return false;
  collection.prepend(key, `${usrBin};`);
  return true;
}

module.exports = { PYTHON, detectPython, GDB_PYTHON_ENV, pathKey, gitUsrBin, toolEnv, taskEnv, applyTerminalEnv };
