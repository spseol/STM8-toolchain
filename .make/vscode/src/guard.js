'use strict';

const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Reading some registers clears flags (UART1->DR clears RXNE). A hover over such a register
 * would read it behind the student's back. Returns "UART1.DR" (or "UART1" for the whole
 * peripheral) when EXPRESSION would read such a register, otherwise null.
 * sideEffects: { UART1: ["DR"], ... }
 */
function guardsHover(expression, sideEffects) {
  for (const [periph, regs] of Object.entries(sideEffects)) {
    const pattern = new RegExp(`\\b${escape(periph)}\\b(?:\\s*(?:->|\\.)\\s*(\\w+))?`, 'g');
    for (const match of expression.matchAll(pattern)) {
      const before = expression.slice(0, match.index).trimEnd();
      if (before.endsWith('&') && !before.endsWith('&&')) continue; // address-of reads nothing
      if (match[1] === undefined) return periph;
      if (regs.includes(match[1])) return `${periph}.${match[1]}`;
    }
  }
  return null;
}

// Used when the register model cannot be loaded. Must equal READ_SIDE_EFFECT in .make/stm8sfr.py
// (test_fallback_side_effects_match_python).
const DEFAULT_SIDE_EFFECTS = {
  UART1: ['DR'], UART2: ['DR'], UART3: ['DR'], UART4: ['DR'],
  SPI: ['DR'], I2C: ['DR', 'SR3'], FLASH: ['IAPSR'], AWU: ['CSR'],
};

module.exports = { guardsHover, DEFAULT_SIDE_EFFECTS };
