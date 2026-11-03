'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { chipItems, registerStatusBar } = require('../src/statusbar');

const DEVICES = {
  'Value line': { STM8S003F3: 'stm8s003f3', STM8S003K3: 'stm8s003f3' },
  'Access line': { STM8S103F3: 'stm8s103f2' },
};

test('chip_items_group_by_family_and_mark_the_current_chip', () => {
  const items = chipItems(DEVICES, 'stm8s103f3');
  assert.deepStrictEqual(items.map((i) => i.label), ['Value line', 'STM8S003F3', 'STM8S003K3', 'Access line', 'STM8S103F3']);
  assert.strictEqual(items[0].kind, -1); // separator
  assert.strictEqual(items[3].kind, -1);
  assert.deepStrictEqual(items.map((i) => Boolean(i.picked)), [false, false, false, false, true]);
});

function setup({
  session, chosen, info = { deviceFlash: 'stm8s208rb' }, afterSuccess, activeTerminal, terminals = [], executeTask, ...stubs
} = {}) {
  const seen = {
    items: [], commands: {}, executed: [], tasks: [], listeners: [], messages: [], switched: [], quickPicks: [], changed: 0,
  };
  const folder = { uri: { fsPath: '/proj' } };
  const vscode = {
    StatusBarAlignment: { Left: 1 },
    window: {
      createStatusBarItem: () => { const item = { show() { this.shown = true; }, dispose() {} }; seen.items.push(item); return item; },
      activeTerminal,
      terminals,
      showQuickPick: async (items, options) => { seen.quickPicks.push({ items, options }); return chosen; },
      showWarningMessage: async (text) => seen.messages.push(['warning', text]),
      showErrorMessage: async (text) => seen.messages.push(['error', text]),
      showInformationMessage: async (text) => seen.messages.push(['info', text]),
    },
    commands: {
      registerCommand: (id, handler) => { seen.commands[id] = handler; return { dispose() {} }; },
      executeCommand: async (...args) => seen.executed.push(args),
    },
    debug: { activeDebugSession: session },
    TaskScope: { Workspace: 2 },
    TaskRevealKind: { Always: 1 },
    TaskPanelKind: { Shared: 1 },
    Task: class { constructor(definition, scope, name, source, execution, problemMatchers) { Object.assign(this, { definition, scope, name, source, execution, problemMatchers }); } },
    ShellExecution: class { constructor(commandLine, options) { this.commandLine = commandLine; this.options = options; } },
    workspace: {
      workspaceFolders: [folder],
      getConfiguration: (section) => ({ get: (key, fallback) => (section === 'stm8' && key === 'afterSuccess' && afterSuccess) || fallback }),
    },
    tasks: {
      executeTask: executeTask || (async (task) => { seen.tasks.push(task); }),
      onDidEndTaskProcess: (listener) => {
        const registration = { listener, disposed: false, dispose() { this.disposed = true; } };
        seen.listeners.push(registration);
        return registration;
      },
    },
  };
  const project = {
    readProjectInfo: async () => { if (info instanceof Error) throw info; return info; },
    listChips: async () => DEVICES,
    switchChip: async (root, chip) => seen.switched.push([root, chip]),
    ...stubs,
  };
  const bar = registerStatusBar(vscode, project, { rootOf: () => '/proj', onChipChanged: () => { seen.changed++; } });
  seen.folder = folder;
  // a task of the extension ends with EXITCODE (listeners already disposed do not hear it, like in VS Code)
  seen.end = async (exitCode, task = seen.tasks[seen.tasks.length - 1]) => {
    for (const registration of [...seen.listeners]) {
      if (!registration.disposed) registration.listener({ execution: { task }, exitCode });
    }
    await settle();
  };
  return { vscode, seen, bar };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

test('four_items_with_commands_and_the_current_chip', async () => {
  const { seen } = setup();
  await settle();
  assert.deepStrictEqual(seen.items.map((i) => i.command), ['stm8.build', 'stm8.flash', 'stm8.debug', 'stm8.pickChip']);
  assert.deepStrictEqual(seen.items.map((i) => i.shown), [true, true, true, true]);
  assert.match(seen.items[3].text, /STM8S208RB/);
});

test('old_toolchain_shows_a_question_mark', async () => {
  const { seen } = setup({ info: new Error('Old toolchain') });
  await settle();
  assert.match(seen.items[3].text, /STM8 \?/);
});

test('build_and_flash_run_make_as_a_task_in_the_project_folder', async () => {
  const { seen } = setup();
  await seen.commands['stm8.build']();
  await seen.commands['stm8.flash']();
  assert.deepStrictEqual(seen.tasks.map((t) => [t.name, t.source, t.execution.commandLine]),
    [['make', 'stm8', 'make'], ['make flash', 'stm8', 'make flash']]);
  const [task] = seen.tasks;
  assert.strictEqual(task.execution.options.cwd, '/proj');
  assert.strictEqual(task.scope, seen.folder);
  assert.deepStrictEqual(task.problemMatchers, ['$sdcc']);
  assert.strictEqual(task.presentationOptions.reveal, 1);
  assert.strictEqual(task.presentationOptions.focus, true);
  assert.deepStrictEqual(seen.executed, []);
});

test('task_without_a_matching_workspace_folder_uses_the_workspace_scope', async () => {
  const { vscode, seen } = setup();
  vscode.workspace.workspaceFolders = [{ uri: { fsPath: '/other' } }];
  await seen.commands['stm8.build']();
  assert.strictEqual(seen.tasks[0].scope, 2);
});

test('debug_starts_debugging', async () => {
  const { seen } = setup();
  await seen.commands['stm8.debug']();
  assert.deepStrictEqual(seen.executed, [['workbench.action.debug.start']]);
});

const SWITCHING = ['workbench.action.closePanel', 'workbench.action.focusActiveEditorGroup'];
const ids = (seen) => seen.executed.map(([id]) => id);

test('success_closes_the_panel_and_focuses_the_editor_by_default', async () => {
  const { seen } = setup();
  await seen.commands['stm8.build']();
  assert.deepStrictEqual(ids(seen), []); // nothing before make ends
  await seen.end(0);
  assert.deepStrictEqual(ids(seen), SWITCHING);
});

test('success_with_editor_only_focuses_the_editor', async () => {
  const { seen } = setup({ afterSuccess: 'editor' });
  await seen.commands['stm8.flash']();
  await seen.end(0);
  assert.deepStrictEqual(ids(seen), ['workbench.action.focusActiveEditorGroup']);
});

test('success_with_stay_does_nothing', async () => {
  const { seen } = setup({ afterSuccess: 'stay' });
  await seen.commands['stm8.build']();
  await seen.end(0);
  assert.deepStrictEqual(ids(seen), []);
});

test('success_with_previous_terminal_shows_the_terminal_active_before', async () => {
  const previous = { shown: 0, show() { this.shown++; } };
  const { seen } = setup({ afterSuccess: 'previousTerminal', activeTerminal: previous, terminals: [previous] });
  await seen.commands['stm8.build']();
  await seen.end(0);
  assert.strictEqual(previous.shown, 1);
  assert.deepStrictEqual(ids(seen), []);
});

test('previous_terminal_closed_or_missing_falls_back_to_the_editor', async () => {
  const closed = { exitStatus: { code: undefined }, show() { throw new Error('closed'); } };
  const gone = { show() { throw new Error('not in window.terminals'); } };
  for (const options of [{ activeTerminal: closed, terminals: [closed] }, { activeTerminal: gone, terminals: [] }, {}]) {
    const { seen } = setup({ afterSuccess: 'previousTerminal', ...options });
    await seen.commands['stm8.build']();
    await seen.end(0);
    assert.deepStrictEqual(ids(seen), ['workbench.action.focusActiveEditorGroup']);
  }
});

test('failure_or_cancel_keeps_the_terminal_in_front', async () => {
  for (const exitCode of [1, 2, undefined]) {
    const { seen } = setup();
    await seen.commands['stm8.flash']();
    await seen.end(exitCode);
    assert.deepStrictEqual(ids(seen), [], `exit code ${exitCode}`);
  }
});

test('listener_ignores_other_tasks_and_is_disposed_after_its_own', async () => {
  const { seen } = setup();
  await seen.commands['stm8.build']();
  const mine = seen.tasks[0];
  await seen.end(0, { name: 'build', source: 'stm8' }); // stm8: build of F5
  await seen.end(0, { name: 'make', source: 'Workspace' });
  assert.deepStrictEqual(ids(seen), []);
  assert.strictEqual(seen.listeners[0].disposed, false);
  await seen.end(0, mine);
  assert.deepStrictEqual(ids(seen), SWITCHING);
  assert.strictEqual(seen.listeners[0].disposed, true);
});

test('failed_task_start_shows_the_error_and_disposes_the_listener', async () => {
  const { seen } = setup({ executeTask: async () => { throw new Error('no shell'); } });
  await seen.commands['stm8.build']();
  assert.ok(seen.messages.some(([kind, text]) => kind === 'error' && /no shell/.test(text)));
  assert.strictEqual(seen.listeners[0].disposed, true);
});

test('flash_during_debugging_restarts_the_session', async () => {
  const { seen } = setup({ session: { type: 'stm8' } });
  await seen.commands['stm8.flash']();
  assert.deepStrictEqual(seen.executed, [['workbench.action.debug.restart']]);
  assert.deepStrictEqual(seen.tasks, []);
});

test('pick_chip_switches_and_updates_the_item', async () => {
  const { seen } = setup({ chosen: { label: 'STM8S103F3' } });
  await settle();
  await seen.commands['stm8.pickChip']();
  assert.deepStrictEqual(seen.switched, [['/proj', 'stm8s103f3']]);
  assert.strictEqual(seen.changed, 1);
  assert.ok(seen.items[3].text.includes('STM8S208RB') || seen.items[3].text.includes('STM8S103F3'));
  assert.ok(seen.messages.some(([kind, text]) => kind === 'info' && /STM8S103F3/.test(text)));
  assert.match(seen.quickPicks[0].options.placeHolder, /STM8S208RB/);
});

test('pick_chip_updates_the_item_from_the_project', async () => {
  let current = { deviceFlash: 'stm8s208rb' };
  const { seen } = setup({
    chosen: { label: 'STM8S103F3' },
    readProjectInfo: async () => current,
    switchChip: async () => { current = { deviceFlash: 'stm8s103f3' }; },
  });
  await settle();
  await seen.commands['stm8.pickChip']();
  assert.match(seen.items[3].text, /STM8S103F3/);
});

test('pick_chip_same_chip_changes_nothing', async () => {
  const { seen } = setup({ chosen: { label: 'STM8S208RB' } });
  await seen.commands['stm8.pickChip']();
  assert.deepStrictEqual(seen.switched, []);
});

test('pick_chip_cancelled_changes_nothing', async () => {
  const { seen } = setup({ chosen: undefined });
  await seen.commands['stm8.pickChip']();
  assert.deepStrictEqual(seen.switched, []);
});

test('pick_chip_refuses_during_debugging', async () => {
  const { seen } = setup({ session: { type: 'stm8' }, chosen: { label: 'STM8S103F3' } });
  await seen.commands['stm8.pickChip']();
  assert.deepStrictEqual(seen.switched, []);
  assert.deepStrictEqual(seen.quickPicks, []);
  assert.ok(seen.messages.some(([kind, text]) => kind === 'warning' && /Stop debugging/.test(text)));
});

test('pick_chip_failure_is_shown', async () => {
  const { seen } = setup({
    chosen: { label: 'STM8S103F3' },
    switchChip: async () => { throw new Error('Cannot switch to stm8s103f3: nope'); },
  });
  await seen.commands['stm8.pickChip']();
  assert.ok(seen.messages.some(([kind, text]) => kind === 'error' && /nope/.test(text)));
  assert.strictEqual(seen.changed, 0);
});
