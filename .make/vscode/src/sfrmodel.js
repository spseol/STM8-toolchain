'use strict';

const lowBit = (mask) => 31 - Math.clz32(mask & -mask);

/** The JSON line `sfr-json` printed → { periphs, sideEffects: { UART1: ["DR"] }, running }. */
function parse(text) {
  const line = text.split('\n').find((candidate) => candidate.startsWith('{'));
  if (!line) throw new Error(`No JSON in the output of sfr-json: ${text.trim().slice(0, 200)}`);
  const model = JSON.parse(line);
  const sideEffects = {};
  for (const periph of model.periphs) {
    const names = periph.regs.filter((reg) => reg.sideEffect).map((reg) => reg.name);
    if (names.length) sideEffects[periph.name] = names;
  }
  return { periphs: model.periphs, sideEffects, running: Boolean(model.running) };
}

const isSingleBit = (bit) => (bit.mask & (bit.mask - 1)) === 0;
const fieldValue = (bit, value) => (value & bit.mask) >>> lowBit(bit.mask);
const withField = (old, bit, value) => (old & ~bit.mask & 0xff) | ((value << lowBit(bit.mask)) & bit.mask);

const hex = (value) => `0x${value.toString(16).padStart(2, '0')}`;
const binary = (value) => `${(value >> 4).toString(2).padStart(4, '0')} ${(value & 15).toString(2).padStart(4, '0')}`;
const byMaskDescending = (bits) => [...bits].sort((a, b) => b.mask - a.mask);

/** "0x81  1000 0001  ARPE PSC=1 CEN": value, binary, the set bits (multi-bit fields as NAME=value). */
function regLabel(reg) {
  if (reg.value === null || reg.value === undefined) return '';
  const names = [];
  for (const bit of byMaskDescending(reg.bits)) {
    const value = fieldValue(bit, reg.value);
    if (!value) continue;
    names.push(isSingleBit(bit) ? bit.name : `${bit.name}=${value}`);
  }
  return [hex(reg.value), binary(reg.value), ...(names.length ? [names.join(' ')] : [])].join('  ');
}

/** Mask of the bits that differ from the previous stop (0 when nothing is known). */
function changedBits(reg) {
  if (reg.value === null || reg.value === undefined || reg.prev === null || reg.prev === undefined) return 0;
  return (reg.value ^ reg.prev) & 0xff;
}

module.exports = { parse, isSingleBit, fieldValue, withField, regLabel, changedBits, byMaskDescending, lowBit };
