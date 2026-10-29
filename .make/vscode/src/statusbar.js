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
    item(100, 'stm8.build', '$(tools) Build', 'Build the project (make debug-files)'),
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

  let terminal;
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
    vscode.commands.registerCommand('stm8.build', () => vscode.commands.executeCommand('workbench.action.tasks.runTask', 'stm8: build')),
    vscode.commands.registerCommand('stm8.debug', () => vscode.commands.executeCommand('workbench.action.debug.start')),
    vscode.commands.registerCommand('stm8.flash', () => {
      if (debugging()) return vscode.commands.executeCommand('workbench.action.debug.restart'); // the debugger loads the chip
      terminal = terminal || vscode.window.createTerminal({ name: 'STM8 flash', cwd: rootOf() });
      terminal.show();
      terminal.sendText('make flash');
      return undefined;
    }),
    vscode.commands.registerCommand('stm8.pickChip', pickChip),
  ];
  updateChip();
  return { updateChip, dispose: () => [...bars, ...commands].forEach((disposable) => disposable.dispose()) };
}

module.exports = { chipItems, registerStatusBar };
