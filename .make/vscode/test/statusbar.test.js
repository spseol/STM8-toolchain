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

function setup({ session, chosen, info = { deviceFlash: 'stm8s208rb' }, ...stubs } = {}) {
  const seen = { items: [], commands: {}, executed: [], terminals: [], messages: [], switched: [], quickPicks: [], changed: 0 };
  const vscode = {
    StatusBarAlignment: { Left: 1 },
    window: {
      createStatusBarItem: () => { const item = { show() { this.shown = true; }, dispose() {} }; seen.items.push(item); return item; },
      createTerminal: (options) => {
        const terminal = { options, sent: [], sendText(text) { this.sent.push(text); }, show() {}, dispose() {} };
        seen.terminals.push(terminal);
        return terminal;
      },
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
  };
  const project = {
    readProjectInfo: async () => { if (info instanceof Error) throw info; return info; },
    listChips: async () => DEVICES,
    switchChip: async (root, chip) => seen.switched.push([root, chip]),
    ...stubs,
  };
  const bar = registerStatusBar(vscode, project, { rootOf: () => '/proj', onChipChanged: () => { seen.changed++; } });
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

test('build_runs_the_build_task', async () => {
  const { seen } = setup();
  await seen.commands['stm8.build']();
  assert.deepStrictEqual(seen.executed, [['workbench.action.tasks.runTask', 'stm8: build']]);
});

test('debug_starts_debugging', async () => {
  const { seen } = setup();
  await seen.commands['stm8.debug']();
  assert.deepStrictEqual(seen.executed, [['workbench.action.debug.start']]);
});

test('flash_without_session_runs_make_flash_in_one_reused_terminal', async () => {
  const { seen } = setup();
  await seen.commands['stm8.flash']();
  await seen.commands['stm8.flash']();
  assert.strictEqual(seen.terminals.length, 1);
  assert.strictEqual(seen.terminals[0].options.cwd, '/proj');
  assert.deepStrictEqual(seen.terminals[0].sent, ['make flash', 'make flash']);
  assert.deepStrictEqual(seen.executed, []);
});

test('flash_recreates_the_terminal_after_it_was_closed', async () => {
  const { seen } = setup();
  await seen.commands['stm8.flash']();
  seen.terminals[0].exitStatus = { code: undefined }; // closed with the trash icon
  await seen.commands['stm8.flash']();
  assert.strictEqual(seen.terminals.length, 2);
  assert.deepStrictEqual(seen.terminals[0].sent, ['make flash']);
  assert.deepStrictEqual(seen.terminals[1].sent, ['make flash']);
});

test('flash_during_debugging_restarts_the_session', async () => {
  const { seen } = setup({ session: { type: 'stm8' } });
  await seen.commands['stm8.flash']();
  assert.deepStrictEqual(seen.executed, [['workbench.action.debug.restart']]);
  assert.strictEqual(seen.terminals.length, 0);
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
