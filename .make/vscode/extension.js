'use strict';
const crypto = require('node:crypto');
const path = require('node:path');
const vscode = require('vscode');
const { GdbProxy } = require('./src/adapter');
const { DEFAULT_SIDE_EFFECTS } = require('./src/guard');
const { SfrTree } = require('./src/sfrtree');
const { renderRegisterHtml } = require('./src/regview');
const { registerStatusBar } = require('./src/statusbar');
const project = require('./src/project'); // called through the object, so the tests can replace functions
const upgrade = require('./src/upgrade');
const newproject = require('./src/newproject');
const { registerBuildTask } = require('./src/tasks');

const TYPE = 'stm8';
const RESUMING = new Set(['continue', 'next', 'stepIn', 'stepOut', 'stepBack', 'reverseContinue']);
const UPDATE = 'Update Toolchain';
const SWITCH = 'Switch to Makefile-sdcc';
const DISMISSED = 'stm8.upgrade.dismissed'; // workspaceState: the student chose "Don't ask again"
const DEFAULT_CONFIG = { type: TYPE, request: 'launch', name: 'STM8 debug', preLaunchTask: 'stm8: build' };

const rootOf = (folder) => (folder || (vscode.workspace.workspaceFolders || [])[0] || {}).uri?.fsPath;

function activate(context) {
  const output = vscode.window.createOutputChannel('STM8 debug');

  // --- peripheral registers (SFR) ---------------------------------------------------------
  const evaluate = async (expression) => {
    const session = vscode.debug.activeDebugSession;
    if (!session || session.type !== TYPE) throw new Error('No STM8 debug session is running.');
    return (await session.customRequest('evaluate', { expression, context: 'repl' })).result;
  };
  const tree = new SfrTree(vscode, evaluate);
  const view = vscode.window.createTreeView('stm8Peripherals', { treeDataProvider: tree });
  const report = (error) => vscode.window.showErrorMessage(error.message);
  const guarded = async (action) => {
    try {
      await action();
    } catch (error) {
      report(error);
    }
  };
  const ask = async (node, what) => vscode.window.showInputBox({
    prompt: `${what} (decimal, 0x hex or 0b binary)`,
    placeHolder: node.reg.value === null || node.reg.value === undefined ? '' : `now ${node.reg.value}`,
  });

  // detail of one register in an editor tab; follows the tree
  let panel = null; // { view, periph, reg }
  const showRegister = () => {
    const state = panel && tree.regState(panel.periph, panel.reg);
    if (state) {
      panel.view.webview.html = renderRegisterHtml(state.periph, state.reg, crypto.randomBytes(16).toString('hex'), { running: tree.running });
    }
  };
  tree.onDidChangeTreeData(showRegister);
  const openRegister = (node) => {
    if (panel) panel.view.dispose();
    const view = vscode.window.createWebviewPanel(
      'stm8Register', `${node.periph.name}->${node.reg.name}`, vscode.ViewColumn.Beside, { enableScripts: true },
    );
    const mine = { view, periph: node.periph.name, reg: node.reg.name };
    panel = mine;
    tree.pin(mine.periph);
    view.onDidDispose(() => {
      tree.unpin(mine.periph);
      if (panel === mine) panel = null;
    });
    view.webview.onDidReceiveMessage((msg) => guarded(async () => {
      const state = tree.regState(mine.periph, mine.reg);
      const bit = state.reg.bits.find((candidate) => candidate.name === msg.name);
      const fieldNode = { kind: 'bit', periph: state.periph, reg: state.reg, bit };
      if (msg.type === 'setBit') {
        await tree.setField(fieldNode, String(msg.value));
      } else if (msg.type === 'editField') {
        const text = await ask(fieldNode, `Write ${mine.periph}->${mine.reg} field ${bit.name}`);
        if (text) await tree.setField(fieldNode, text);
      }
    }));
    showRegister();
  };

  view.onDidExpandElement(({ element }) => {
    if (element.kind !== 'periph') return;
    tree.expand(element.periph.name);
    guarded(() => tree.refresh());
  });
  view.onDidCollapseElement(({ element }) => {
    if (element.kind === 'periph') tree.collapse(element.periph.name);
  });
  view.onDidChangeCheckboxState(async ({ items }) => {
    for (const [node, state] of items) {
      await guarded(() => tree.toggleBit(node, state === vscode.TreeItemCheckboxState.Checked));
    }
  });

  // exit code of the last run of every task: after a failed preLaunchTask VS Code offers "Debug Anyway"
  const builds = new Map();
  const configProvider = {
    resolveDebugConfiguration(folder, config) {
      return config.type ? config : { ...DEFAULT_CONFIG }; // F5 without launch.json
    },
    // after preLaunchTask, so the ELF exists
    async resolveDebugConfigurationWithSubstitutedVariables(folder, config) {
      const root = rootOf(folder);
      if (config.preLaunchTask && builds.has(config.preLaunchTask) && builds.get(config.preLaunchTask) !== 0) {
        // conflict markers in the Makefile break the build ("missing separator"): say what is really wrong
        const conflict = project.makefileConflictError(root);
        await vscode.window.showErrorMessage(
          conflict ? conflict.message : 'The build failed, so the chip would get an old program. Fix the errors (Problems panel) and press F5 again.',
          { modal: true },
        );
        return undefined;
      }
      try {
        const problems = await project.preflight(await project.readProjectInfo(root), root);
        if (problems.length === 0) return config;
        await vscode.window.showErrorMessage(`STM8 debug cannot start:\n- ${problems.join('\n- ')}`, { modal: true });
      } catch (error) {
        const fix = error.fix === 'updateToolchain' ? [UPDATE] : [];
        const choice = await vscode.window.showErrorMessage(error.message, { modal: true }, ...fix);
        if (choice === UPDATE) vscode.commands.executeCommand('stm8.updateToolchain'); // not awaited: the launch is cancelled meanwhile
      }
      return undefined; // cancels the launch
    },
  };

  const adapterFactory = {
    async createDebugAdapterDescriptor(session) {
      const root = rootOf(session.workspaceFolder);
      const info = await project.readProjectInfo(root);
      let model = null;
      try {
        model = await project.loadSfrModel(info, root);
      } catch (error) {
        output.append(`${error.message}\n`); // debugging works without the register view
      }
      tree.setModel(model);
      const messages = new vscode.EventEmitter();
      const proxy = new GdbProxy({
        project: info,
        sideEffects: model ? model.sideEffects : DEFAULT_SIDE_EFFECTS,
        spawn: () => project.spawnGdb(info, root),
        send: (msg) => messages.fire(msg),
        openocdTail: () => project.openocdTail(info.openocdLog),
        otherOpenocd: project.otherOpenocd,
        log: (text) => output.append(text),
      });
      return new vscode.DebugAdapterInlineImplementation({
        onDidSendMessage: messages.event,
        handleMessage: (msg) => proxy.handleMessage(msg),
        dispose: () => {
          proxy.dispose();
          messages.dispose();
        },
      });
    },
  };

  // --- Update Toolchain -----------------------------------------------------------------------
  const switchQuestion = (variant) => `This project uses the older toolchain variant ${variant}.\n\n`
    + 'The update replaces its Makefile with the toolchain\'s Makefile-sdcc. Only the chip (DEVICE_FLASH) is carried over; '
    + 'other edits in the Makefile (for example F_CPU or paths) are NOT. '
    + 'The old Makefile stays recoverable with `git checkout Makefile`.';
  const withProgress = (title, task) => (vscode.window.withProgress
    ? vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title }, task)
    : task());

  async function showUpgradeResult(root, result) {
    if (result.code === 0) {
      const summary = result.output.split('\n').filter((line) => !line.startsWith('Nothing was committed')).join('\n');
      await vscode.window.showInformationMessage(
        `Toolchain updated.\n${summary}\nNothing was committed – review the changes (git diff) and commit them when you are happy.`,
      );
    } else if (result.code === 2 && result.conflict) {
      const document = await vscode.workspace.openTextDocument(path.join(root, 'Makefile'));
      await vscode.window.showTextDocument(document);
      await vscode.window.showWarningMessage(
        'The toolchain was updated, but your Makefile and the new one disagree. The Makefile now contains conflict markers '
        + '(<<<<<<<, =======, >>>>>>>). Choose Accept Current/Incoming for each one and save; the project will not build until the markers are gone.'
        + `${result.output ? `\n${result.output}` : ''}`,
      );
    } else {
      await vscode.window.showErrorMessage(result.output || `Update Toolchain failed (code ${result.code}).`);
    }
  }

  async function updateToolchain() {
    const session = vscode.debug.activeDebugSession;
    if (session && session.type === TYPE) {
      await vscode.window.showWarningMessage('Stop debugging before updating the toolchain.');
      return;
    }
    const root = rootOf();
    if (!root) { // execFile would run git and python3 in the cwd of the editor (maybe $HOME)
      await vscode.window.showWarningMessage('Open the STM8 project folder first.');
      return;
    }
    const url = vscode.workspace.getConfiguration('stm8').get('toolchainUrl');
    const go = (switchChoice) => withProgress('Updating the STM8 toolchain…', () => upgrade.runUpgrade(root, { url, switchChoice }));
    let result = await go();
    if (result.code === 3) {
      const choice = await vscode.window.showWarningMessage(switchQuestion(result.needsSwitch), { modal: true }, SWITCH);
      if (choice !== SWITCH) return;
      result = await go('yes');
      if (result.code === 3) result = { code: 1, output: 'The update still asks to switch the Makefile; nothing was changed.' };
    }
    await showUpgradeResult(root, result);
  }

  const tracker = {
    createDebugAdapterTracker() {
      return {
        onWillReceiveMessage(msg) {
          if (msg.type === 'request' && RESUMING.has(msg.command)) tree.setRunning(true);
        },
        onDidSendMessage(msg) {
          if (msg.type !== 'event') return;
          if (msg.event === 'stopped') guarded(() => tree.refresh());
          else if (msg.event === 'continued') tree.setRunning(true);
        },
      };
    },
  };

  context.subscriptions.push(
    output,
    view,
    registerBuildTask(vscode),
    vscode.tasks.onDidEndTaskProcess((event) => {
      const { name, source } = event.execution.task;
      builds.set(name, event.exitCode);
      builds.set(`${source}: ${name}`, event.exitCode); // preLaunchTask names a provider task by its label
    }),
    vscode.debug.registerDebugConfigurationProvider(TYPE, configProvider),
    vscode.debug.registerDebugAdapterDescriptorFactory(TYPE, adapterFactory),
    vscode.debug.registerDebugAdapterTrackerFactory(TYPE, tracker),
    vscode.debug.onDidTerminateDebugSession((session) => {
      if (session.type === TYPE) tree.setModel(null);
    }),
    vscode.commands.registerCommand('stm8.sfr.writeRegister', async (node) => {
      const text = await ask(node, `Write ${node.periph.name}->${node.reg.name}`);
      if (text) await guarded(() => tree.writeRegister(node, text));
    }),
    vscode.commands.registerCommand('stm8.sfr.editField', async (node) => {
      const text = await ask(node, `Write ${node.periph.name}->${node.reg.name} field ${node.bit.name}`);
      if (text) await guarded(() => tree.setField(node, text));
    }),
    vscode.commands.registerCommand('stm8.sfr.readRegister', (node) => guarded(() => tree.readRegister(node))),
    vscode.commands.registerCommand('stm8.sfr.openRegister', openRegister),
    vscode.commands.registerCommand('stm8.updateToolchain', () => guarded(updateToolchain)),
    vscode.commands.registerCommand('stm8.newProject', () => guarded(
      () => newproject.newProjectFlow(vscode, { createProject: (options) => newproject.createProject(options), context }),
    )),
  );

  context.subscriptions.push(registerStatusBar(vscode, project, {
    rootOf: () => rootOf(),
    onChipChanged: () => tree.setModel(null),
  }));

  const version = context.extension.packageJSON.version;
  const notice = project.versionNotice(version, rootOf());
  if (notice) vscode.window.showInformationMessage(notice);

  if (project.upgradeOffer(version, rootOf()) && !context.workspaceState.get(DISMISSED)) {
    guarded(async () => {
      const choice = await vscode.window.showInformationMessage(
        'This project has an older STM8 toolchain than the extension. Update it?', UPDATE, 'Not now', "Don't ask again",
      );
      if (choice === UPDATE) await vscode.commands.executeCommand('stm8.updateToolchain');
      else if (choice === "Don't ask again") await context.workspaceState.update(DISMISSED, true);
    });
  }
}

function deactivate() {}

module.exports = { activate, deactivate };
