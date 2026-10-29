'use strict';
const { parse, isSingleBit, fieldValue, regLabel, changedBits, byMaskDescending, lowBit } = require('./sfrmodel');

const isRunningError = (error) => /notStopped|running/i.test(error.message || '');
const hex4 = (value) => `0x${value.toString(16).padStart(4, '0')}`;

/**
 * Tree of the peripheral registers: peripheral → register → bit field. The structure comes from
 * the offline model, the values are read (`sfr-json`) only for expanded peripherals when the
 * program stops. api: the `vscode` module. evaluate(expression): repl command → its output.
 */
class SfrTree {
  constructor(api, evaluate) {
    this.api = api;
    this.evaluate = evaluate;
    this.model = null;
    this.running = false;
    this.expanded = new Set();
    this.pinned = new Map(); // peripheral -> how many panels show one of its registers
    this.resumes = 0; // counts resumes, so a refresh that started before one cannot clear 'running'
    this.values = new Map(); // register address -> { value, prev }
    this.emitter = new api.EventEmitter();
    this.onDidChangeTreeData = this.emitter.event;
  }

  setModel(model) {
    this.model = model;
    this.values.clear();
    this.running = false;
    this.emitter.fire();
  }

  setRunning(running) {
    if (running) this.resumes += 1;
    this.running = running;
    this.emitter.fire();
  }

  expand(name) {
    this.expanded.add(name);
  }

  collapse(name) {
    this.expanded.delete(name);
  }

  /** A detail panel shows a register of NAME: keep it fresh although the tree node is collapsed. */
  pin(name) {
    this.pinned.set(name, (this.pinned.get(name) || 0) + 1);
  }

  unpin(name) {
    const count = (this.pinned.get(name) || 0) - 1;
    if (count > 0) this.pinned.set(name, count);
    else this.pinned.delete(name);
  }

  /** Reads the expanded peripherals again (the program has stopped). */
  async refresh() {
    if (!this.model) return;
    const generation = this.resumes;
    try {
      for (const name of new Set([...this.expanded, ...this.pinned.keys()])) await this.fetch(name);
      if (generation === this.resumes) this.running = false;
    } catch (error) {
      if (!isRunningError(error)) throw error;
      this.running = true;
    } finally {
      this.emitter.fire();
    }
  }

  async fetch(name) {
    const text = await this.evaluate(`sfr-json ${name}`);
    this.store(name, parse(text), true);
  }

  store(name, parsed, replace) {
    const fresh = parsed.periphs.find((periph) => periph.name === name);
    const known = this.model.periphs.find((periph) => periph.name === name);
    if (replace) for (const reg of known.regs) this.values.delete(reg.addr);
    for (const reg of fresh.regs) {
      if (reg.value !== null) this.values.set(reg.addr, { value: reg.value, prev: reg.prev });
    }
  }

  /** The register with its latest values, for the detail panel; null when the model has no such register. */
  regState(periphName, regName) {
    const periph = this.model && this.model.periphs.find((candidate) => candidate.name === periphName);
    const reg = periph && periph.regs.find((candidate) => candidate.name === regName);
    return reg ? { periph, reg: { ...reg, ...this.values.get(reg.addr) } } : null;
  }

  async readRegister(node) {
    const text = await this.evaluate(`sfr-json ${node.periph.name}.${node.reg.name}`);
    this.store(node.periph.name, parse(text), false);
    this.emitter.fire();
  }

  async writeRegister(node, text) {
    await this.write(node.periph.name, `${node.periph.name}.${node.reg.name} ${text.trim()}`);
  }

  async setField(node, text) {
    await this.write(node.periph.name, `${node.periph.name}.${node.reg.name}.${node.bit.name} ${text.trim()}`);
  }

  async toggleBit(node, checked) {
    await this.setField(node, checked ? '1' : '0');
  }

  async write(periphName, target) {
    await this.evaluate(`sfr-set ${target}`);
    await this.fetch(periphName);
    this.emitter.fire();
  }

  // --- TreeDataProvider ---------------------------------------------------------------------

  getChildren(node) {
    if (!this.model) return [];
    if (!node) {
      return [...this.model.periphs].sort((a, b) => a.base - b.base).map((periph) => ({ kind: 'periph', periph }));
    }
    if (node.kind === 'periph') {
      return node.periph.regs.map((reg) => ({
        kind: 'reg', periph: node.periph, reg: { ...reg, ...this.values.get(reg.addr) },
      }));
    }
    if (node.kind === 'reg') {
      return byMaskDescending(node.reg.bits).map((bit) => ({ kind: 'bit', periph: node.periph, reg: node.reg, bit }));
    }
    return [];
  }

  getTreeItem(node) {
    const { TreeItem, TreeItemCollapsibleState: State } = this.api;
    if (node.kind === 'periph') {
      const item = new TreeItem(node.periph.name, State.Collapsed);
      item.id = node.periph.name;
      item.description = hex4(node.periph.base);
      item.contextValue = 'stm8.periph';
      return item;
    }
    if (node.kind === 'reg') return this.regItem(node);
    return this.bitItem(node);
  }

  regItem({ periph, reg }) {
    const { TreeItem, TreeItemCollapsibleState: State, ThemeIcon, ThemeColor } = this.api;
    const item = new TreeItem(reg.name, reg.bits.length ? State.Collapsed : State.None);
    item.id = `${periph.name}.${reg.name}`;
    if (this.running) item.description = 'running';
    else if (reg.value === null || reg.value === undefined) {
      item.description = reg.sideEffect ? 'not read (reading clears flags)' : '';
    } else item.description = regLabel(reg);
    item.tooltip = `${periph.name}->${reg.name}  ${hex4(reg.addr)}${reg.desc ? `\n${reg.desc}` : ''}`
      + `${reg.reset === null ? '' : `\nreset value 0x${reg.reset.toString(16).padStart(2, '0')}`}`;
    if (!this.running && changedBits(reg)) item.iconPath = new ThemeIcon('circle-filled', new ThemeColor('charts.yellow'));
    item.contextValue = reg.sideEffect ? 'stm8.reg.sideEffect' : 'stm8.reg';
    return item;
  }

  bitItem({ periph, reg, bit }) {
    const { TreeItem, TreeItemCollapsibleState: State, TreeItemCheckboxState: Checkbox } = this.api;
    const low = lowBit(bit.mask);
    const high = 31 - Math.clz32(bit.mask);
    const item = new TreeItem(`${high === low ? low : `${high}:${low}`} ${bit.name}`, State.None);
    item.id = `${periph.name}.${reg.name}.${bit.name}`;
    item.tooltip = bit.desc;
    // a field write reads the register first: not for registers whose read clears flags
    const editable = !reg.sideEffect;
    item.contextValue = `${isSingleBit(bit) ? 'stm8.bit' : 'stm8.field'}${editable ? '' : '.readOnly'}`;
    const known = !this.running && reg.value !== null && reg.value !== undefined;
    if (known) {
      const value = fieldValue(bit, reg.value);
      item.description = String(value);
      if (isSingleBit(bit) && editable) item.checkboxState = value ? Checkbox.Checked : Checkbox.Unchecked;
    }
    return item;
  }
}

module.exports = { SfrTree };
