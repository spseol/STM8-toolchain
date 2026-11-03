'use strict';

const SEPARATOR = -1; // vscode.QuickPickItemKind.Separator

/** QuickPick items: a separator per family, then its chips; the current chip is preselected. */
function chipItems(devices, current) {
  const items = [];
  for (const [family, chips] of Object.entries(devices)) {
    items.push({ label: family, kind: SEPARATOR });
    for (const [chip, datasheet] of Object.entries(chips)) {
      items.push({ label: chip, description: datasheet, picked: chip.toLowerCase() === current.toLowerCase() });
    }
  }
  return items;
}

/**
 * Build, Flash, Debug and the chip in the status bar. project: { readProjectInfo, listChips,
 * switchChip }. rootOf(): the project folder. onChipChanged(): the register model is stale now.
 * Returns { dispose, updateChip }.
 */
function registerStatusBar(vscode, project, { rootOf, onChipChanged }) {
  const debugging = () => {
    const session = vscode.debug.activeDebugSession;
    return Boolean(session) && session.type === 'stm8';
  };
  const item = (priority, command, text, tooltip) => {
    const bar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, priority);
    Object.assign(bar, { command, text, tooltip });
    bar.show();
    return bar;
  };
  const bars = [
    item(100, 'stm8.build', '$(tools) Build', 'Build the project (make)'),
    item(99, 'stm8.flash', '$(zap) Flash', 'Build and load the program into the chip'),
    item(98, 'stm8.debug', '$(debug-alt) Debug', 'Build, load and debug (F5)'),
    item(97, 'stm8.pickChip', '$(chip) STM8', 'Choose the target chip'),
  ];
  const chipBar = bars[3];

  async function updateChip() {
    try {
      chipBar.text = `$(chip) ${(await project.readProjectInfo(rootOf())).deviceFlash.toUpperCase()}`;
    } catch {
      chipBar.text = '$(chip) STM8 ?';
    }
  }

  /** Where to go after make ended with exit code 0 (setting stm8.afterSuccess). previous: the terminal active before. */
  async function afterSuccess(previous) {
    const mode = vscode.workspace.getConfiguration('stm8').get('afterSuccess', 'hidePanel');
    const focusEditor = () => vscode.commands.executeCommand('workbench.action.focusActiveEditorGroup');
    if (mode === 'hidePanel') {
      await vscode.commands.executeCommand('workbench.action.closePanel');
      await focusEditor();
    } else if (mode === 'editor') {
      await focusEditor();
    } else if (mode === 'previousTerminal') {
      const alive = previous && previous.exitStatus === undefined && vscode.window.terminals.includes(previous);
      if (alive) previous.show();
      else await focusEditor();
    }
  }

  /**
   * Runs COMMANDLINE as a task `stm8: NAME` in the project folder. The task gives the exit code
   * (a terminal with sendText() does not), so a successful run can switch back, see afterSuccess().
   */
  async function runTask(name, commandLine) {
    const root = rootOf();
    const folder = (vscode.workspace.workspaceFolders || []).find((candidate) => candidate.uri.fsPath === root);
    const task = new vscode.Task(
      { type: 'stm8', command: commandLine }, folder || vscode.TaskScope.Workspace, name, 'stm8',
      new vscode.ShellExecution(commandLine, { cwd: root }),
      ['$sdcc'], // the same problem matcher as stm8: build (package.json)
    );
    task.presentationOptions = {
      reveal: vscode.TaskRevealKind.Always, focus: true, panel: vscode.TaskPanelKind.Shared, showReuseMessage: false,
    };
    const previous = vscode.window.activeTerminal;
    // only while the task runs: a permanent listener would not be the only one for onDidEndTaskProcess
    const listener = vscode.tasks.onDidEndTaskProcess((event) => {
      const ended = event.execution.task;
      if (ended.source !== 'stm8' || ended.name !== name) return;
      listener.dispose();
      if (event.exitCode === 0) afterSuccess(previous).catch((error) => vscode.window.showErrorMessage(error.message));
    });
    try {
      await vscode.tasks.executeTask(task);
    } catch (error) {
      listener.dispose();
      vscode.window.showErrorMessage(error.message);
    }
  }

  async function pickChip() {
    if (debugging()) {
      await vscode.window.showWarningMessage('Stop debugging before changing the chip.');
      return;
    }
    const root = rootOf();
    try {
      const [devices, info] = await Promise.all([project.listChips(root), project.readProjectInfo(root)]);
      const picked = await vscode.window.showQuickPick(chipItems(devices, info.deviceFlash), {
        placeHolder: `Target chip (now ${info.deviceFlash.toUpperCase()})`,
      });
      if (!picked || picked.label.toLowerCase() === info.deviceFlash.toLowerCase()) return;
      await project.switchChip(root, picked.label.toLowerCase());
      await updateChip();
      onChipChanged();
      vscode.window.showInformationMessage(`Target chip is now ${picked.label}. The project is rebuilt by Build or F5.`);
    } catch (error) {
      vscode.window.showErrorMessage(error.message);
    }
  }

  const commands = [
    vscode.commands.registerCommand('stm8.build', () => runTask('make', 'make')),
    vscode.commands.registerCommand('stm8.debug', () => vscode.commands.executeCommand('workbench.action.debug.start')),
    vscode.commands.registerCommand('stm8.flash', () => {
      if (debugging()) return vscode.commands.executeCommand('workbench.action.debug.restart'); // the debugger loads the chip
      return runTask('make flash', 'make flash');
    }),
    vscode.commands.registerCommand('stm8.pickChip', pickChip),
  ];
  updateChip();
  return { updateChip, dispose: () => [...bars, ...commands].forEach((disposable) => disposable.dispose()) };
}

module.exports = { chipItems, registerStatusBar };
