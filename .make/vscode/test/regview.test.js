'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { renderRegisterHtml } = require('../src/regview');

const periph = { name: 'TIM4', base: 0x5340 };
const reg = (extra = {}) => ({
  name: 'CR1', addr: 0x5340, reset: 0, desc: 'control register 1', value: 0x81, prev: 0x01,
  bits: [
    { name: 'ARPE', mask: 0x80, desc: 'Auto-Reload Preload Enable' },
    { name: 'PSC', mask: 0x0e, desc: 'Prescaler' },
    { name: 'CEN', mask: 0x01, desc: 'Counter Enable' },
  ],
  ...extra,
});
const html = (extra, nonce = 'abc123') => renderRegisterHtml(periph, reg(extra), nonce);

test('escapes_html_in_descriptions', () => {
  const out = html({ desc: '<script>alert(1)</script>', bits: [{ name: 'X', mask: 1, desc: '<img src=x onerror=1>' }] });
  assert.ok(!out.includes('<script>alert'));
  assert.ok(!out.includes('<img src=x'));
  assert.ok(out.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
});

test('shows_header_reset_value_and_current_value', () => {
  const out = html();
  assert.ok(out.includes('TIM4-&gt;CR1'));
  assert.ok(out.includes('0x5340'));
  assert.match(out, /reset value <b>0x00<\/b>/);
  assert.match(out, /value <b>0x81<\/b> \(1000 0001\)/);
});

test('multibit_position_and_single_bit_position', () => {
  const out = html();
  assert.match(out, /<td class="pos">3:1<\/td>/);
  assert.match(out, /<td class="pos">7<\/td>/);
});

test('single_bit_values_are_clickable_and_carry_the_new_value', () => {
  const set = html(); // 0x81: ARPE and CEN are set, a click clears them
  assert.match(set, /data-bit="ARPE" data-value="0"/);
  assert.match(set, /data-bit="CEN" data-value="0"/);
  assert.match(set, /data-field="PSC"/); // multi-bit field: edited through an input box
  assert.match(html({ value: 0 }), /data-bit="ARPE" data-value="1"/); // clear: a click sets it
});

test('csp_allows_only_the_nonce_and_no_external_resources', () => {
  const out = html({}, 'n0nce');
  assert.match(out, /Content-Security-Policy/);
  assert.match(out, /default-src 'none'; style-src 'nonce-n0nce'; script-src 'nonce-n0nce'/);
  assert.ok(!/https?:/.test(out));
  assert.strictEqual((out.match(/<script nonce="n0nce">/g) || []).length, 1);
});

test('unread_register_says_so_and_has_no_click_targets', () => {
  const out = html({ value: null, prev: null, sideEffect: true });
  assert.match(out, /not read/);
  assert.ok(!out.includes('data-bit='));
});

test('running_program_disables_editing', () => {
  const out = renderRegisterHtml(periph, reg(), 'n', { running: true });
  assert.match(out, /running/);
  assert.ok(!out.includes('data-bit='));
});

test('side_effect_register_is_display_only', () => {
  const out = html({ sideEffect: true });
  assert.ok(!out.includes('data-bit='));
  assert.ok(!out.includes('data-field='));
  assert.match(out, /reading it clears flags/);
});
