#!/usr/bin/env node
'use strict';
// GdbProxy as a DAP server on stdio, for the tests (VS Code runs the proxy inside the extension).
// Run in the project folder. STM8_DAP_INFO_OVERRIDE (JSON) replaces fields of `make dap-info`.
const { GdbProxy } = require('../src/adapter');
const { createParser, encode } = require('../src/dapframe');
const { DEFAULT_SIDE_EFFECTS } = require('../src/guard');
const { readProjectInfo, loadSfrModel, openocdTail, otherOpenocd, spawnGdb } = require('../src/project');

async function main() {
  const cwd = process.cwd();
  const info = { ...(await readProjectInfo(cwd)), ...JSON.parse(process.env.STM8_DAP_INFO_OVERRIDE || '{}') };
  const model = await loadSfrModel(info, cwd).catch(() => null); // debugging works without it
  const proxy = new GdbProxy({
    project: info,
    sideEffects: model ? model.sideEffects : DEFAULT_SIDE_EFFECTS,
    spawn: () => spawnGdb(info, cwd),
    send: (msg) => process.stdout.write(encode(msg)),
    openocdTail: () => openocdTail(info.openocdLog),
    otherOpenocd,
    log: (text) => process.stderr.write(text),
  });
  const parser = createParser((msg) => proxy.handleMessage(msg));
  process.stdin.on('data', (chunk) => parser.push(chunk));
  process.stdin.on('end', () => proxy.dispose());
  proxy.gdb.on('exit', () => setTimeout(() => process.exit(0), 100));
}

main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exit(1);
});
