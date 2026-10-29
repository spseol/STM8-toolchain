'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { guardsHover, DEFAULT_SIDE_EFFECTS } = require('../src/guard');

const sideEffects = { UART1: ['DR'], SPI: ['DR'] };

test('register_read_is_guarded', () => {
  assert.strictEqual(guardsHover('UART1->DR', sideEffects), 'UART1.DR');
  assert.strictEqual(guardsHover('UART1.DR', sideEffects), 'UART1.DR');
  assert.strictEqual(guardsHover('x + UART1->DR', sideEffects), 'UART1.DR');
  assert.strictEqual(guardsHover('SPI -> DR', sideEffects), 'SPI.DR');
});

test('whole_peripheral_is_guarded', () => {
  assert.strictEqual(guardsHover('UART1', sideEffects), 'UART1');
});

test('harmless_expressions_pass', () => {
  assert.strictEqual(guardsHover('UART1->SR', sideEffects), null);
  assert.strictEqual(guardsHover('GPIOA->ODR', sideEffects), null);
  assert.strictEqual(guardsHover('UART1_SR_TXE', sideEffects), null);
  assert.strictEqual(guardsHover('counter', sideEffects), null);
});

test('address_of_reads_nothing', () => {
  assert.strictEqual(guardsHover('&UART1->DR', sideEffects), null);
  assert.strictEqual(guardsHover('p + &UART1->DR', sideEffects), null);
  assert.strictEqual(guardsHover('a && UART1->DR', sideEffects), 'UART1.DR');
});

test('default_side_effects_cover_the_known_registers', () => {
  assert.deepStrictEqual(DEFAULT_SIDE_EFFECTS.UART1, ['DR']);
  assert.deepStrictEqual(DEFAULT_SIDE_EFFECTS.I2C, ['DR', 'SR3']);
  assert.strictEqual(guardsHover('UART1->DR', DEFAULT_SIDE_EFFECTS), 'UART1.DR');
});
