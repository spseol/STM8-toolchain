'use strict';
const test = require('node:test');
const assert = require('node:assert');
const Module = require('node:module');
const { PassThrough } = require('node:stream');

// extension.js needs the `vscode` module, which only exists inside the editor: a small fake.
function load() {
  const seen = { providers: {}, factories: {}, trackers: {}, commands: {}, views: {}, panels: [], messages: [] };
  class EventEmitter {
    constructor() {
      this.listeners = [];
      this.event = (listener) => this.listeners.push(listener);
    }
    fire(message) { this.listeners.forEach((listener) => listener(message)); }
    dispose() {}
  }
  const vscode = {
    debug: {
      activeDebugSession: undefined,
      registerDebugConfigurationProvider: (type, provider) => { seen.providers[type] = provider; return { dispose() {} }; },
      registerDebugAdapterDescriptorFactory: (type, factory) => { seen.factories[type] = factory; return { dispose() {} }; },
      registerDebugAdapterTrackerFactory: (type, factory) => { seen.trackers[type] = factory; return { dispose() {} }; },
      onDidTerminateDebugSession: (listener) => { seen.terminated = listener; return { dispose() {} }; },
    },
    commands: {
      registerCommand: (id, handler) => { seen.commands[id] = handler; return { dispose() {} }; },
      executeCommand: async () => {},
    },
    StatusBarAlignment: { Left: 1 },
    tasks: { onDidEndTaskProcess: (listener) => { seen.taskEnded = listener; return { dispose() {} }; } },
    ViewColumn: { Beside: -2 },
    TreeItem: class { constructor(label, collapsibleState) { this.label = label; this.collapsibleState = collapsibleState; } },
    TreeItemCollapsibleState: { None: 0, Collapsed: 1 },
    TreeItemCheckboxState: { Unchecked: 0, Checked: 1 },
    ThemeIcon: class {},
    ThemeColor: class {},
    window: {
      createTreeView: (id, options) => {
        const view = {
          id, options, handlers: {},
          onDidExpandElement: (h) => { view.handlers.expand = h; return { dispose() {} }; },
          onDidCollapseElement: (h) => { view.handlers.collapse = h; return { dispose() {} }; },
          onDidChangeCheckboxState: (h) => { view.handlers.checkbox = h; return { dispose() {} }; },
          dispose() {},
        };
        seen.views[id] = view;
        return view;
      },
      createStatusBarItem: () => ({ show() {}, dispose() {} }),
      createTerminal: () => ({ show() {}, sendText() {}, dispose() {} }),
      showQuickPick: async () => undefined,
      showWarningMessage: async () => {},
      showInputBox: async () => seen.inputText,
      createWebviewPanel: (id, title, column, options) => {
        const panel = {
          id, title, options, handlers: {}, webview: { html: '' }, disposed: false,
          onDidDispose: (h) => { panel.handlers.dispose = h; return { dispose() {} }; },
          dispose() { panel.disposed = true; if (panel.handlers.dispose) panel.handlers.dispose(); },
        };
        panel.webview.onDidReceiveMessage = (h) => { panel.handlers.message = h; return { dispose() {} }; };
        seen.panels.push(panel);
        return panel;
      },
      showErrorMessage: async (...args) => { seen.messages.push(['error', ...args]); },
      showInformationMessage: async (...args) => { seen.messages.push(['info', ...args]); },
      createOutputChannel: () => ({ append() {}, dispose() {} }),
    },
    workspace: { workspaceFolders: [{ uri: { fsPath: '/proj' } }] },
    EventEmitter,
    DebugAdapterInlineImplementation: class { constructor(adapter) { this.adapter = adapter; } },
  };
  const originalLoad = Module._load;
  Module._load = function (request, ...rest) {
    return request === 'vscode' ? vscode : originalLoad.call(this, request, ...rest);
  };
  try {
    delete require.cache[require.resolve('../extension')];
    return { extension: require('../extension'), project: require('../src/project'), seen, vscode };
  } finally {
    Module._load = originalLoad;
  }
}

const context = () => ({ subscriptions: [], extension: { packageJSON: { version: '0.1.0' } } });
const folder = { uri: { fsPath: '/proj' } };
const config = { type: 'stm8', request: 'launch', name: 'STM8 debug' };

test('registers_provider_and_factory', () => {
  const { extension, project, seen } = load();
  project.versionNotice = () => null;
  extension.activate(context());
  assert.ok(seen.providers.stm8);
  assert.ok(seen.factories.stm8);
});

test('empty_configuration_gets_defaults', () => {
  const { extension, project, seen } = load();
  project.versionNotice = () => null;
  extension.activate(context());
  assert.deepStrictEqual(seen.providers.stm8.resolveDebugConfiguration(undefined, {}), {
    type: 'stm8', request: 'launch', name: 'STM8 debug', preLaunchTask: 'stm8: build',
  });
});

test('preflight_problems_abort_launch', async () => {
  const { extension, project, seen } = load();
  project.versionNotice = () => null;
  project.readProjectInfo = async () => ({ elf: '/x' });
  project.preflight = async () => ['openocd not found in PATH', 'No ST-Link found'];
  extension.activate(context());
  const result = await seen.providers.stm8.resolveDebugConfigurationWithSubstitutedVariables(folder, { ...config });
  assert.strictEqual(result, undefined);
  const [kind, text, options] = seen.messages.find(([k]) => k === 'error');
  assert.strictEqual(kind, 'error');
  assert.match(text, /openocd not found in PATH/);
  assert.match(text, /No ST-Link found/);
  assert.deepStrictEqual(options, { modal: true });
});

test('toolchain_error_aborts_launch_with_its_message', async () => {
  const { extension, project, seen } = load();
  project.versionNotice = () => null;
  project.readProjectInfo = async () => { throw new project.ToolchainError('Old toolchain – update .make/'); };
  extension.activate(context());
  const result = await seen.providers.stm8.resolveDebugConfigurationWithSubstitutedVariables(folder, { ...config });
  assert.strictEqual(result, undefined);
  assert.match(seen.messages.find(([k]) => k === 'error')[1], /Old toolchain/);
});

test('no_problems_passes_configuration', async () => {
  const { extension, project, seen } = load();
  project.versionNotice = () => null;
  project.readProjectInfo = async () => ({ elf: '/x' });
  project.preflight = async () => [];
  extension.activate(context());
  assert.deepStrictEqual(
    await seen.providers.stm8.resolveDebugConfigurationWithSubstitutedVariables(folder, { ...config }), config);
});

test('factory_returns_inline_adapter', async () => {
  const { extension, project, seen } = load();
  project.versionNotice = () => null;
  project.readProjectInfo = async () => ({ elf: '/x', openocdLog: '/x/log', gdbTarget: '|' });
  project.spawnGdb = () => Object.assign(new PassThrough(), {
    stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(),
    on() {}, exitCode: null, signalCode: null, kill() {},
  });
  extension.activate(context());
  const descriptor = await seen.factories.stm8.createDebugAdapterDescriptor({ workspaceFolder: folder, configuration: config });
  assert.strictEqual(typeof descriptor.adapter.handleMessage, 'function');
  assert.strictEqual(typeof descriptor.adapter.onDidSendMessage, 'function');
  descriptor.adapter.dispose();
});

test('version_notice_is_shown_when_project_is_newer', () => {
  const { extension, project, seen } = load();
  project.versionNotice = () => 'The project has a newer STM8 extension';
  extension.activate(context());
  assert.ok(seen.messages.some(([kind, text]) => kind === 'info' && /newer STM8 extension/.test(text)));
});

const MODEL = {
  periphs: [{
    name: 'TIM4', base: 0x5340, other: [],
    regs: [{ name: 'CR1', addr: 0x5340, reset: 0, desc: '', sideEffect: false, value: null, prev: null, bits: [{ name: 'CEN', mask: 1, desc: '' }] }],
  }, {
    name: 'UART1', base: 0x5230, other: [],
    regs: [{ name: 'DR', addr: 0x5231, reset: 0, desc: '', sideEffect: true, value: null, prev: null, bits: [] }],
  }],
  sideEffects: { UART1: ['DR'] },
};
const TIM4_JSON = JSON.stringify({
  running: false,
  periphs: [{ ...MODEL.periphs[0], regs: [{ ...MODEL.periphs[0].regs[0], value: 1, prev: 1 }] }],
});
const tim4Cr1 = { kind: 'reg', periph: MODEL.periphs[0], reg: MODEL.periphs[0].regs[0] };
const flush = () => new Promise((resolve) => setImmediate(resolve));

function fakeGdb() {
  return Object.assign(new PassThrough(), {
    stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(),
    on() {}, exitCode: null, signalCode: null, kill() {},
  });
}

/** Extension activated, debug session started; vscode.debug.activeDebugSession records the repl requests. */
async function started(overrides = {}) {
  const loaded = load();
  const { extension, project, seen, vscode } = loaded;
  project.versionNotice = () => null;
  project.readProjectInfo = async () => ({ elf: '/x', openocdLog: '/x/log', gdbTarget: '|' });
  project.loadSfrModel = overrides.loadSfrModel || (async () => MODEL);
  project.spawnGdb = fakeGdb;
  extension.activate(context());
  const descriptor = await seen.factories.stm8.createDebugAdapterDescriptor({ workspaceFolder: folder, configuration: config });
  const requests = [];
  vscode.debug.activeDebugSession = {
    type: 'stm8',
    customRequest: async (command, args) => {
      requests.push([command, args.expression]);
      return { result: args.expression.startsWith('sfr-json') ? TIM4_JSON : '1' };
    },
  };
  return { ...loaded, descriptor, requests, tree: seen.views.stm8Peripherals.options.treeDataProvider };
}

test('registers_the_peripherals_view_and_commands', () => {
  const { extension, project, seen } = load();
  project.versionNotice = () => null;
  extension.activate(context());
  assert.ok(seen.views.stm8Peripherals);
  for (const id of ['stm8.sfr.writeRegister', 'stm8.sfr.editField', 'stm8.sfr.readRegister', 'stm8.sfr.openRegister']) assert.ok(seen.commands[id], id);
  assert.ok(seen.trackers.stm8);
});

test('registers_the_status_bar_commands', () => {
  const { extension, project, seen } = load();
  project.versionNotice = () => null;
  project.readProjectInfo = async () => ({ deviceFlash: 'stm8s208rb' });
  extension.activate(context());
  for (const id of ['stm8.build', 'stm8.flash', 'stm8.debug', 'stm8.pickChip']) assert.ok(seen.commands[id], id);
});

test('changing_the_chip_drops_the_register_model', async () => {
  const { extension, project, seen, vscode } = load();
  project.versionNotice = () => null;
  project.readProjectInfo = async () => ({ deviceFlash: 'stm8s208rb' });
  project.listChips = async () => ({ 'Access line': { STM8S103F3: 'x' } });
  project.switchChip = async () => {};
  extension.activate(context());
  const tree = seen.views.stm8Peripherals.options.treeDataProvider;
  tree.setModel(MODEL);
  assert.strictEqual(tree.getChildren().length, 2);
  vscode.window.showQuickPick = async () => ({ label: 'STM8S103F3' });
  await seen.commands['stm8.pickChip']();
  assert.deepStrictEqual(tree.getChildren(), []);
});

test('session_start_guards_hover_with_the_model_side_effects', async () => {
  const { descriptor } = await started();
  const sent = [];
  descriptor.adapter.onDidSendMessage((msg) => sent.push(msg));
  descriptor.adapter.handleMessage({ seq: 5, type: 'request', command: 'evaluate', arguments: { expression: 'UART1->DR', context: 'hover' } });
  assert.match(sent[0].body.result, /not read/);
  descriptor.adapter.dispose();
});

test('model_load_failure_does_not_stop_debugging', async () => {
  const { descriptor, tree } = await started({ loadSfrModel: async () => { throw new Error('Cannot load the peripheral registers: x'); } });
  assert.strictEqual(typeof descriptor.adapter.handleMessage, 'function');
  assert.deepStrictEqual(tree.getChildren(), []);
  descriptor.adapter.dispose();
});

test('stop_event_refreshes_expanded_peripherals_only', async () => {
  const { seen, requests, tree } = await started();
  seen.views.stm8Peripherals.handlers.expand({ element: { kind: 'periph', periph: MODEL.periphs[0] } });
  await flush();
  requests.length = 0;
  seen.trackers.stm8.createDebugAdapterTracker({}).onDidSendMessage({ type: 'event', event: 'stopped' });
  await flush();
  assert.deepStrictEqual(requests, [['evaluate', 'sfr-json TIM4']]); // UART1 is collapsed: DR is not touched
  assert.strictEqual(tree.running, false);
});

test('resuming_marks_the_tree_as_running', async () => {
  const { seen, tree } = await started();
  const tracker = seen.trackers.stm8.createDebugAdapterTracker({});
  tracker.onWillReceiveMessage({ type: 'request', command: 'next' });
  assert.strictEqual(tree.running, true);
  tracker.onWillReceiveMessage({ type: 'request', command: 'variables' });
  assert.strictEqual(tree.running, true); // other requests do not matter
});

test('terminated_session_clears_the_tree', async () => {
  const { seen, tree } = await started();
  assert.strictEqual(tree.getChildren().length, 2);
  seen.terminated({ type: 'stm8' });
  assert.deepStrictEqual(tree.getChildren(), []);
});

test('write_register_command_asks_for_a_value_and_writes_it', async () => {
  const { seen, requests } = await started();
  seen.inputText = '0x21';
  await seen.commands['stm8.sfr.writeRegister'](tim4Cr1);
  assert.deepStrictEqual(requests.map((r) => r[1]), ['sfr-set TIM4.CR1 0x21', 'sfr-json TIM4']);
});

test('cancelled_input_writes_nothing', async () => {
  const { seen, requests } = await started();
  seen.inputText = undefined;
  await seen.commands['stm8.sfr.writeRegister'](tim4Cr1);
  assert.deepStrictEqual(requests, []);
});

test('checkbox_toggle_writes_the_bit', async () => {
  const { seen, requests } = await started();
  const bit = { kind: 'bit', periph: MODEL.periphs[0], reg: MODEL.periphs[0].regs[0], bit: MODEL.periphs[0].regs[0].bits[0] };
  await seen.views.stm8Peripherals.handlers.checkbox({ items: [[bit, 1]] });
  assert.strictEqual(requests[0][1], 'sfr-set TIM4.CR1.CEN 1');
});

test('write_error_is_shown_to_the_student', async () => {
  const { seen, vscode } = await started();
  vscode.debug.activeDebugSession.customRequest = async () => { throw new Error('Program is running, pause it first.'); };
  seen.inputText = '1';
  await seen.commands['stm8.sfr.writeRegister'](tim4Cr1);
  assert.match(seen.messages.find(([kind]) => kind === 'error')[1], /Program is running/);
});

test('open_register_shows_a_panel_with_the_register', async () => {
  const { seen } = await started();
  await seen.commands['stm8.sfr.openRegister'](tim4Cr1);
  const [panel] = seen.panels;
  assert.strictEqual(panel.options.enableScripts, true);
  assert.match(panel.webview.html, /TIM4-&gt;CR1/);
  assert.match(panel.webview.html, /Content-Security-Policy/);
});

test('opening_another_register_replaces_the_panel', async () => {
  const { seen } = await started();
  await seen.commands['stm8.sfr.openRegister'](tim4Cr1);
  await seen.commands['stm8.sfr.openRegister'](tim4Cr1);
  assert.strictEqual(seen.panels.length, 2);
  assert.strictEqual(seen.panels[0].disposed, true);
});

test('panel_click_on_a_bit_writes_it', async () => {
  const { seen, requests } = await started();
  await seen.commands['stm8.sfr.openRegister'](tim4Cr1);
  await seen.panels[0].handlers.message({ type: 'setBit', name: 'CEN', value: 1 });
  assert.strictEqual(requests[0][1], 'sfr-set TIM4.CR1.CEN 1');
});

test('panel_follows_the_tree_after_a_stop', async () => {
  const { seen, tree } = await started();
  seen.views.stm8Peripherals.handlers.expand({ element: { kind: 'periph', periph: MODEL.periphs[0] } });
  await flush();
  await seen.commands['stm8.sfr.openRegister'](tim4Cr1);
  const before = seen.panels[0].webview.html;
  await tree.refresh(); // reads TIM4 (CR1 = 1) and fires the change event
  assert.notStrictEqual(seen.panels[0].webview.html, before);
  assert.match(seen.panels[0].webview.html, /value <b>0x01<\/b>/);
});

test('model_load_failure_keeps_the_hover_guard', async () => {
  const { descriptor } = await started({ loadSfrModel: async () => { throw new Error('Cannot load the peripheral registers: x'); } });
  const sent = [];
  descriptor.adapter.onDidSendMessage((msg) => sent.push(msg));
  descriptor.adapter.handleMessage({ seq: 5, type: 'request', command: 'evaluate', arguments: { expression: 'UART1->DR', context: 'hover' } });
  assert.match(sent[0].body.result, /not read/);
  descriptor.adapter.dispose();
});

test('panel_keeps_its_peripheral_fresh_after_the_tree_node_is_collapsed', async () => {
  const { seen, requests } = await started();
  const view = seen.views.stm8Peripherals;
  view.handlers.expand({ element: { kind: 'periph', periph: MODEL.periphs[0] } });
  await seen.commands['stm8.sfr.openRegister'](tim4Cr1);
  view.handlers.collapse({ element: { kind: 'periph', periph: MODEL.periphs[0] } });
  await flush();
  requests.length = 0;
  seen.trackers.stm8.createDebugAdapterTracker({}).onDidSendMessage({ type: 'event', event: 'stopped' });
  await flush();
  assert.deepStrictEqual(requests, [['evaluate', 'sfr-json TIM4']]);
  seen.panels[0].dispose(); // closing the panel releases the peripheral
  requests.length = 0;
  seen.trackers.stm8.createDebugAdapterTracker({}).onDidSendMessage({ type: 'event', event: 'stopped' });
  await flush();
  assert.deepStrictEqual(requests, []);
});

test('failed_build_blocks_debug_anyway', async () => {
  const { extension, project, seen } = load();
  project.versionNotice = () => null;
  project.readProjectInfo = async () => ({ elf: '/x' });
  project.preflight = async () => [];
  extension.activate(context());
  const withTask = { ...config, preLaunchTask: 'stm8: build' };
  const resolve = () => seen.providers.stm8.resolveDebugConfigurationWithSubstitutedVariables(folder, { ...withTask });
  seen.taskEnded({ execution: { task: { name: 'stm8: build' } }, exitCode: 2 });
  assert.strictEqual(await resolve(), undefined);
  assert.match(seen.messages.find(([kind]) => kind === 'error')[1], /build failed/i);
  seen.taskEnded({ execution: { task: { name: 'stm8: build' } }, exitCode: 0 });
  assert.deepStrictEqual(await resolve(), withTask);
});

test('other_tasks_do_not_block_the_launch', async () => {
  const { extension, project, seen } = load();
  project.versionNotice = () => null;
  project.readProjectInfo = async () => ({ elf: '/x' });
  project.preflight = async () => [];
  extension.activate(context());
  seen.taskEnded({ execution: { task: { name: 'lint' } }, exitCode: 1 });
  const withTask = { ...config, preLaunchTask: 'stm8: build' };
  assert.deepStrictEqual(
    await seen.providers.stm8.resolveDebugConfigurationWithSubstitutedVariables(folder, { ...withTask }), withTask);
});
