'use strict';
const { encode, createParser } = require('./dapframe');
const { guardsHover } = require('./guard');

const OWN_SEQ_START = 1000000; // proxy's own requests to gdb never collide with VS Code's seq numbers
const HOVER_TEXT = 'not read – reading clears flags; use the Read icon in the STM8 Peripherals view';
const BUSY_HINT = 'ST-Link may be in use by another OpenOCD or debug session (make debug / make openocd).';

/** A path as one word for the gdb CLI (gdb splits unquoted paths at spaces). */
const gdbQuote = (file) => `"${file.replace(/(["\\])/g, '\\$1')}"`;

/**
 * Sits between VS Code and `stm8-gdb -i dap`:
 *  - turns `launch` into gdb's `attach` (the chip is already there, gdb must not `run`),
 *  - after `configurationDone` loads the program and runs to main() with the repl command `run`,
 *  - answers hovers over registers whose read clears flags without reading them,
 *  - turns every failure, timeout or crash of gdb into a message and `terminated`, never a hang.
 *
 * project: output of `make dap-info`. spawn(): the gdb child process. send(msg): to VS Code.
 * sideEffects: { UART1: ["DR"] }. openocdTail(): last OpenOCD error lines.
 * otherOpenocd(): is another OpenOCD running?
 */
class GdbProxy {
  constructor({
    project, spawn, send, sideEffects = {}, stepTimeoutMs = 30000,
    openocdTail = () => [], otherOpenocd = async () => false, log = () => {},
  }) {
    Object.assign(this, { project, sideEffects, stepTimeoutMs, openocdTail, otherOpenocd, log });
    this.sendToClient = send;
    this.outSeq = 0;
    this.nextOwnSeq = OWN_SEQ_START;
    this.own = new Map(); // seq -> { step, timer, onOk }
    this.launch = null; // VS Code's launch request while it waits for an answer
    this.configDoneSeq = null;
    this.failed = false;
    this.disposed = false;
    this.disconnecting = false;

    this.gdb = spawn();
    this.parser = createParser((msg) => this.fromGdb(msg));
    this.gdb.stdout.on('data', (chunk) => {
      try {
        this.parser.push(chunk);
      } catch (error) {
        this.fail(`Unreadable message from gdb: ${error.message}`);
      }
    });
    this.gdb.stderr.on('data', (chunk) => this.log(String(chunk)));
    this.gdb.on('exit', (code, signal) => {
      if (!this.disposed && !this.disconnecting) {
        this.fail(`gdb exited unexpectedly (${signal || `code ${code}`})`);
      }
    });
    this.gdb.on('error', (error) => this.fail(`Cannot start stm8-gdb: ${error.message}`));
  }

  /** A message from VS Code. */
  handleMessage(msg) {
    if (this.failed || this.disposed) return;
    if (msg.type === 'request') {
      const args = msg.arguments || {};
      switch (msg.command) {
        case 'launch':
          this.launch = msg;
          this.ownRequest('attach', 'attach', { program: gdbQuote(this.project.elf), target: this.project.gdbTarget }, (reply) => {
            this.answerLaunch({ success: true, body: reply.body });
          });
          return;
        case 'configurationDone':
          this.configDoneSeq = msg.seq;
          break;
        case 'disconnect':
          this.disconnecting = true;
          break;
        case 'evaluate':
          if (args.context === 'hover' && guardsHover(args.expression, this.sideEffects)) {
            this.toClient({
              type: 'response', request_seq: msg.seq, command: 'evaluate', success: true,
              body: { result: HOVER_TEXT, variablesReference: 0 },
            });
            return;
          }
          break;
        default:
      }
    }
    this.toGdb(msg);
  }

  dispose() {
    this.disposed = true;
    this.clearTimers();
    this.killGdb();
  }

  // --- from gdb ---------------------------------------------------------------------------

  fromGdb(msg) {
    if (msg.type === 'response' && this.own.has(msg.request_seq)) {
      const { step, timer, onOk } = this.own.get(msg.request_seq);
      clearTimeout(timer);
      this.own.delete(msg.request_seq);
      if (msg.success) onOk(msg);
      else this.fail(`${step} failed: ${msg.message || 'unknown error'}`);
      return;
    }
    this.toClient(msg);
    if (msg.type === 'response' && msg.request_seq === this.configDoneSeq && msg.success) {
      this.ownRequest('run', 'evaluate', { expression: 'run', context: 'repl' }, () => {});
    }
  }

  answerLaunch(answer) {
    if (!this.launch) return;
    this.toClient({ type: 'response', request_seq: this.launch.seq, command: 'launch', ...answer });
    this.launch = null;
  }

  // --- plumbing ---------------------------------------------------------------------------

  /** A request of the proxy itself: failure or no answer in time ends the session. */
  ownRequest(step, command, args, onOk) {
    const seq = this.nextOwnSeq++;
    const timer = setTimeout(() => this.fail(`${step} timed out after ${this.stepTimeoutMs / 1000} s`), this.stepTimeoutMs);
    this.own.set(seq, { step, timer, onOk });
    this.toGdb({ seq, type: 'request', command, arguments: args });
  }

  toGdb(msg) {
    if (this.gdb.stdin.writable) this.gdb.stdin.write(encode(msg));
  }

  toClient(msg) {
    this.sendToClient({ ...msg, seq: ++this.outSeq });
  }

  clearTimers() {
    for (const { timer } of this.own.values()) clearTimeout(timer);
    this.own.clear();
  }

  killGdb() {
    if (this.gdb.exitCode !== null || this.gdb.signalCode !== null) return;
    this.gdb.kill('SIGTERM');
    setTimeout(() => this.gdb.kill('SIGKILL'), 2000).unref();
  }

  async fail(text) {
    if (this.failed) return;
    this.failed = true;
    this.clearTimers();
    const lines = [text, ...this.openocdTail()];
    if (await this.otherOpenocd().catch(() => false)) lines.push(BUSY_HINT);
    this.answerLaunch({ success: false, message: text });
    this.toClient({ type: 'event', event: 'output', body: { category: 'stderr', output: `${lines.join('\n')}\n` } });
    this.toClient({ type: 'event', event: 'terminated', body: {} });
    this.killGdb();
  }
}

module.exports = { GdbProxy, gdbQuote };
