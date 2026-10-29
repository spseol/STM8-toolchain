'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { parse, regLabel, changedBits, fieldValue, withField, isSingleBit } = require('../src/sfrmodel');

const bits = [
  { name: 'ARPE', mask: 0x80, desc: '' },
  { name: 'PSC', mask: 0x07, desc: '' },
  { name: 'OPM', mask: 0x08, desc: '' },
  { name: 'CEN', mask: 0x01, desc: '' },
];
const reg = (value, prev = null, extra = {}) => ({ name: 'CR1', addr: 0x5340, value, prev, bits, ...extra });

test('reg_label', () => {
  assert.strictEqual(regLabel(reg(0x81)), '0x81  1000 0001  ARPE PSC=1 CEN'); // PSC = bits 2:0 = 1
});

test('reg_label_multibit', () => {
  assert.strictEqual(regLabel(reg(0x05)), '0x05  0000 0101  PSC=5 CEN');
});

test('reg_label_without_value_is_empty', () => {
  assert.strictEqual(regLabel(reg(null)), '');
});

test('changed_bits', () => {
  assert.strictEqual(changedBits(reg(0x81, 0x01)), 0x80);
  assert.strictEqual(changedBits(reg(0x81, null)), 0);
  assert.strictEqual(changedBits(reg(0x81, 0x81)), 0);
  assert.strictEqual(changedBits(reg(null, 0x81)), 0);
});

test('field_value_and_with_field', () => {
  const psc = bits[1];
  assert.strictEqual(fieldValue(psc, 0xAD), 5);
  assert.strictEqual(withField(0xFF, { mask: 0x70 }, 2), 0xAF);
  assert.strictEqual(withField(0x01, { mask: 0x08 }, 1), 0x09);
});

test('is_single_bit', () => {
  assert.strictEqual(isSingleBit(bits[0]), true);
  assert.strictEqual(isSingleBit(bits[1]), false);
});

test('parse_collects_side_effects_and_ignores_text_around_json', () => {
  const model = {
    running: false,
    periphs: [
      { name: 'UART1', base: 0x5230, other: [], regs: [{ name: 'DR', sideEffect: true }, { name: 'SR', sideEffect: false }] },
      { name: 'SPI', base: 0x5200, other: [], regs: [{ name: 'DR', sideEffect: true }] },
      { name: 'TIM4', base: 0x5340, other: [], regs: [{ name: 'CR1', sideEffect: false }] },
    ],
  };
  const parsed = parse(`some banner\n${JSON.stringify(model)}\n`);
  assert.deepStrictEqual(parsed.sideEffects, { UART1: ['DR'], SPI: ['DR'] });
  assert.strictEqual(parsed.periphs.length, 3);
  assert.strictEqual(parsed.running, false);
});

test('parse_without_json_throws', () => {
  assert.throws(() => parse('no json here'), /No JSON/);
});
