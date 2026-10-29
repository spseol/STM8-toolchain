'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { SfrTree } = require('../src/sfrtree');

const api = {
  TreeItem: class { constructor(label, collapsibleState) { this.label = label; this.collapsibleState = collapsibleState; } },
  TreeItemCollapsibleState: { None: 0, Collapsed: 1 },
  TreeItemCheckboxState: { Unchecked: 0, Checked: 1 },
  ThemeIcon: class { constructor(id, color) { this.id = id; this.color = color; } },
  ThemeColor: class { constructor(id) { this.id = id; } },
  EventEmitter: class { constructor() { this.listeners = []; this.event = (l) => this.listeners.push(l); } fire() { this.listeners.forEach((l) => l()); } },
};

const BITS = [{ name: 'ARPE', mask: 0x80, desc: 'preload' }, { name: 'PSC', mask: 0x07, desc: '' }, { name: 'CEN', mask: 0x01, desc: 'enable' }];
const reg = (name, addr, extra = {}) => ({ name, addr, reset: 0, desc: '', sideEffect: false, value: null, prev: null, bits: [], ...extra });
const periph = (name, base, regs) => ({ name, base, regs, other: [] });
const STATIC = {
  periphs: [
    periph('TIM4', 0x5340, [reg('CR1', 0x5340, { bits: BITS })]),
    periph('UART1', 0x5230, [reg('SR', 0x5230), reg('DR', 0x5231, { sideEffect: true })]),
  ],
  sideEffects: { UART1: ['DR'] },
};
const live = (name, regs) => JSON.stringify({ running: false, periphs: [periph(name, STATIC.periphs.find((p) => p.name === name).base, regs)] });

function setup(answers = {}) {
  const calls = [];
  const evaluate = async (expression) => {
    calls.push(expression);
    const answer = answers[expression];
    if (answer instanceof Error) throw answer;
    return answer === undefined ? '' : answer;
  };
  const tree = new SfrTree(api, evaluate);
  tree.setModel(STATIC);
  return { tree, calls };
}

const children = async (tree, node) => tree.getChildren(node);
const items = async (tree, nodes) => nodes.map((n) => tree.getTreeItem(n));

test('root_lists_peripherals_by_address', async () => {
  const { tree } = setup();
  const nodes = await children(tree);
  assert.deepStrictEqual((await items(tree, nodes)).map((i) => i.label), ['UART1', 'TIM4']);
  assert.strictEqual((await items(tree, nodes))[1].description, '0x5340');
});

test('no_values_before_a_peripheral_is_expanded', async () => {
  const { tree } = setup();
  const [uart, tim4] = await children(tree);
  const [cr1] = await children(tree, tim4);
  assert.strictEqual(tree.getTreeItem(cr1).description, '');
  assert.ok(uart);
});

test('values_after_expand_and_refresh', async () => {
  const { tree, calls } = setup({
    'sfr-json TIM4': live('TIM4', [reg('CR1', 0x5340, { bits: BITS, value: 0x81, prev: 0x01 })]),
  });
  tree.expand('TIM4');
  await tree.refresh();
  assert.deepStrictEqual(calls, ['sfr-json TIM4']);
  const tim4 = (await children(tree)).find((n) => n.periph.name === 'TIM4');
  const [cr1] = await children(tree, tim4);
  const item = tree.getTreeItem(cr1);
  assert.strictEqual(item.description, '0x81  1000 0001  ARPE PSC=1 CEN');
  assert.strictEqual(item.iconPath.color.id, 'charts.yellow'); // ARPE changed since the last stop
  const fields = await items(tree, await children(tree, cr1));
  assert.deepStrictEqual(fields.map((f) => f.label), ['7 ARPE', '2:0 PSC', '0 CEN']);
  assert.strictEqual(fields[0].checkboxState, api.TreeItemCheckboxState.Checked);
  assert.strictEqual(fields[2].checkboxState, api.TreeItemCheckboxState.Checked);
  assert.strictEqual(fields[1].checkboxState, undefined); // multi-bit field: edited by command
  assert.strictEqual(fields[1].description, '1'); // PSC = 0x81 & 7
});

test('side_effect_register_is_not_read_until_asked', async () => {
  const { tree, calls } = setup({
    'sfr-json UART1': live('UART1', [reg('SR', 0x5230, { value: 0xC0 }), reg('DR', 0x5231, { sideEffect: true })]),
    'sfr-json UART1.DR': live('UART1', [reg('SR', 0x5230), reg('DR', 0x5231, { sideEffect: true, value: 0x41 })]),
  });
  tree.expand('UART1');
  await tree.refresh();
  const uart = (await children(tree)).find((n) => n.periph.name === 'UART1');
  const [sr, dr] = await children(tree, uart);
  assert.match(tree.getTreeItem(sr).description, /^0xc0/);
  assert.match(tree.getTreeItem(dr).description, /not read/);
  await tree.readRegister(dr);
  assert.ok(calls.includes('sfr-json UART1.DR'));
  const [, readDr] = await children(tree, uart); // the change event makes VS Code ask for new nodes
  assert.match(tree.getTreeItem(readDr).description, /^0x41/);
});

test('running_state_replaces_values', async () => {
  const { tree } = setup({ 'sfr-json TIM4': live('TIM4', [reg('CR1', 0x5340, { bits: BITS, value: 1 })]) });
  tree.expand('TIM4');
  await tree.refresh();
  tree.setRunning(true);
  const tim4 = (await children(tree)).find((n) => n.periph.name === 'TIM4');
  const [cr1] = await children(tree, tim4);
  assert.strictEqual(tree.getTreeItem(cr1).description, 'running');
});

test('not_stopped_error_means_running', async () => {
  const { tree } = setup({ 'sfr-json TIM4': new Error('notStopped') });
  tree.expand('TIM4');
  await tree.refresh(); // must not throw
  assert.strictEqual(tree.running, true);
});

test('toggle_bit_writes_and_rereads', async () => {
  const { tree, calls } = setup({
    'sfr-json TIM4': live('TIM4', [reg('CR1', 0x5340, { bits: BITS, value: 0x01 })]),
  });
  tree.expand('TIM4');
  await tree.refresh();
  const tim4 = (await children(tree)).find((n) => n.periph.name === 'TIM4');
  const [cr1] = await children(tree, tim4);
  const [arpe] = await children(tree, cr1);
  calls.length = 0;
  await tree.toggleBit(arpe, true);
  assert.deepStrictEqual(calls, ['sfr-set TIM4.CR1.ARPE 1', 'sfr-json TIM4']);
  await tree.toggleBit(arpe, false);
  assert.strictEqual(calls[2], 'sfr-set TIM4.CR1.ARPE 0');
});

test('write_register_and_field', async () => {
  const { tree, calls } = setup({ 'sfr-json TIM4': live('TIM4', [reg('CR1', 0x5340, { bits: BITS, value: 0 })]) });
  const tim4 = (await children(tree)).find((n) => n.periph.name === 'TIM4');
  const [cr1] = await children(tree, tim4);
  const [, psc] = await children(tree, cr1);
  await tree.writeRegister(cr1, ' 0x21 ');
  await tree.setField(psc, '5');
  assert.deepStrictEqual(calls.filter((c) => c.startsWith('sfr-set')), ['sfr-set TIM4.CR1 0x21', 'sfr-set TIM4.CR1.PSC 5']);
});

test('collapse_stops_reading_a_peripheral', async () => {
  const { tree, calls } = setup({ 'sfr-json TIM4': live('TIM4', [reg('CR1', 0x5340, { bits: BITS, value: 1 })]) });
  tree.expand('TIM4');
  tree.collapse('TIM4');
  await tree.refresh();
  assert.deepStrictEqual(calls, []);
});

test('reg_state_merges_the_values_for_the_detail_panel', async () => {
  const { tree } = setup({ 'sfr-json TIM4': live('TIM4', [reg('CR1', 0x5340, { bits: BITS, value: 0x81, prev: 1 })]) });
  tree.expand('TIM4');
  await tree.refresh();
  const state = tree.regState('TIM4', 'CR1');
  assert.strictEqual(state.periph.name, 'TIM4');
  assert.strictEqual(state.reg.value, 0x81);
  assert.strictEqual(state.reg.bits.length, 3);
  assert.strictEqual(tree.regState('TIM4', 'NOPE'), null);
});

test('bits_of_a_side_effect_register_are_display_only', async () => {
  const awu = periph('AWU', 0x50f0, [reg('CSR', 0x50f0, { sideEffect: true, bits: [{ name: 'AWUEN', mask: 0x10, desc: '' }, { name: 'TB', mask: 0x0f, desc: '' }], value: 0x10 })]);
  const tree = new SfrTree(api, async () => '');
  tree.setModel({ periphs: [awu], sideEffects: { AWU: ['CSR'] } });
  const [node] = await children(tree);
  const [csr] = await children(tree, node);
  const fields = await items(tree, await children(tree, { ...csr, reg: { ...csr.reg, value: 0x10 } }));
  assert.strictEqual(fields[0].checkboxState, undefined);
  assert.strictEqual(fields[0].contextValue, 'stm8.bit.readOnly');
  assert.strictEqual(fields[1].contextValue, 'stm8.field.readOnly');
});

test('read_only_register_is_display_only', async () => {
  const idr = periph('GPIOA', 0x5000, [reg('IDR', 0x5001, { readOnly: true, value: 1, bits: [{ name: 'PIN0', mask: 1, desc: 'pin 0' }] })]);
  const tree = new SfrTree(api, async () => '');
  tree.setModel({ periphs: [idr], sideEffects: {} });
  const [node] = await children(tree);
  const [regNode] = await children(tree, node);
  assert.strictEqual(tree.getTreeItem(regNode).contextValue, 'stm8.reg.readOnly');
  const [pin] = await items(tree, await children(tree, regNode));
  assert.strictEqual(pin.checkboxState, undefined);
  assert.strictEqual(pin.contextValue, 'stm8.bit.readOnly');
});

// --- review fixes -------------------------------------------------------------------------

test('pinned_peripheral_is_read_although_collapsed', async () => {
  const { tree, calls } = setup({ 'sfr-json TIM4': live('TIM4', [reg('CR1', 0x5340, { bits: BITS, value: 1 })]) });
  tree.pin('TIM4'); // the detail panel shows a register of it
  await tree.refresh();
  assert.deepStrictEqual(calls, ['sfr-json TIM4']);
  tree.unpin('TIM4');
  await tree.refresh();
  assert.deepStrictEqual(calls, ['sfr-json TIM4']);
});

test('resume_during_a_refresh_keeps_the_running_state', async () => {
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const tree = new SfrTree(api, async () => { await pending; return live('TIM4', [reg('CR1', 0x5340, { bits: BITS, value: 1 })]); });
  tree.setModel(STATIC);
  tree.expand('TIM4');
  const refreshing = tree.refresh(); // the program stopped, values are being read
  tree.setRunning(true); // ... and the student pressed continue
  release();
  await refreshing;
  assert.strictEqual(tree.running, true);
});
