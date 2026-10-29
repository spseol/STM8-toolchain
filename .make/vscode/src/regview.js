'use strict';
const { isSingleBit, fieldValue, byMaskDescending, lowBit, changedBits } = require('./sfrmodel');

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (c) => ESCAPES[c]);
const hex = (value, digits = 2) => `0x${value.toString(16).padStart(digits, '0')}`;
const binary = (value) => `${(value >> 4).toString(2).padStart(4, '0')} ${(value & 15).toString(2).padStart(4, '0')}`;

const STYLE = `
  body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 0 1em; }
  h1 small { color: var(--vscode-descriptionForeground); font-weight: normal; }
  table { border-collapse: collapse; margin: 1em 0; }
  th, td { border: 1px solid var(--vscode-panel-border); padding: .25em .6em; text-align: center; }
  td.left, th.left { text-align: left; }
  td.pos { color: var(--vscode-descriptionForeground); }
  .on { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
  .changed { outline: 2px solid var(--vscode-charts-yellow); }
  [data-bit], [data-field] { cursor: pointer; }
  .note { color: var(--vscode-descriptionForeground); }`;

const SCRIPT = `
  const vscode = acquireVsCodeApi();
  document.addEventListener('click', (event) => {
    const bit = event.target.closest('[data-bit]');
    if (bit) vscode.postMessage({ type: 'setBit', name: bit.dataset.bit, value: Number(bit.dataset.value) });
    const field = event.target.closest('[data-field]');
    if (field) vscode.postMessage({ type: 'editField', name: field.dataset.field });
  });`;

/**
 * Detail of one register as an HTML page: value, reset value, the eight bits and the fields with
 * their descriptions. Single-bit values are click targets (toggle), multi-bit fields ask for a value.
 * reg: register with value/prev from sfr-json. options.running: no editing while the program runs.
 */
function renderRegisterHtml(periph, reg, nonce, { running = false } = {}) {
  const known = reg.value !== null && reg.value !== undefined;
  const editable = known && !running && !reg.sideEffect;
  const changed = changedBits(reg);
  const fields = byMaskDescending(reg.bits);

  let state;
  if (running) state = '<p class="note">The program is running; stop it to read or change the register.</p>';
  else if (!known) state = '<p class="note">not read (reading this register clears flags); use the Read icon in the tree.</p>';
  else {
    state = `<p>value <b>${hex(reg.value)}</b> (${binary(reg.value)})</p>`;
    if (reg.sideEffect) state += '<p class="note">Single bits cannot be changed here: reading it clears flags. Write the whole register from the tree instead.</p>';
  }

  const strip = [];
  for (let bit = 7; bit >= 0; bit--) {
    const on = known && (reg.value >> bit) & 1;
    strip.push(`<td class="${on ? 'on' : ''}${changed >> bit & 1 ? ' changed' : ''}">${known ? on : '?'}</td>`);
  }

  const rows = fields.map((field) => {
    const low = lowBit(field.mask);
    const high = 31 - Math.clz32(field.mask);
    const pos = high === low ? `${low}` : `${high}:${low}`;
    const value = known ? fieldValue(field, reg.value) : null;
    let cell;
    if (value === null) cell = '–';
    else if (!editable) cell = String(value);
    else if (isSingleBit(field)) cell = `<span data-bit="${escapeHtml(field.name)}" data-value="${value ? 0 : 1}">${value}</span>`;
    else cell = `<span data-field="${escapeHtml(field.name)}">${value}</span>`;
    return `<tr><td class="pos">${pos}</td><td class="left">${escapeHtml(field.name)}</td>`
      + `<td${value ? ' class="on"' : ''}>${cell}</td><td class="left">${escapeHtml(field.desc)}</td></tr>`;
  });

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}'">
<style nonce="${nonce}">${STYLE}</style></head>
<body>
<h1>${escapeHtml(periph.name)}-&gt;${escapeHtml(reg.name)} <small>${hex(reg.addr, 4)}</small></h1>
<p>${escapeHtml(reg.desc)}</p>
<p>reset value <b>${reg.reset === null || reg.reset === undefined ? '?' : hex(reg.reset)}</b></p>
${state}
<table><tr><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr><tr>${strip.join('')}</tr></table>
<table><thead><tr><th>bits</th><th class="left">field</th><th>value</th><th class="left">description</th></tr></thead>
<tbody>${rows.join('\n')}</tbody></table>
<script nonce="${nonce}">${SCRIPT}</script>
</body></html>
`;
}

module.exports = { renderRegisterHtml };
