'use strict';
// Recommends the CCLS extension (C language server) on activation. A recommendation only: nothing is installed without a click.

const CCLS = 'ccls-project.ccls';
const DISMISSED = 'stm8.ccls.dismissed'; // globalState: the student chose "Don't remind me"
const INSTALL = 'Install CCLS';
const LATER = 'Later';
const NEVER = "Don't remind me";

async function offerCcls(vscode, context) {
  if (vscode.extensions.getExtension(CCLS) || context.globalState.get(DISMISSED)) return;
  const choice = await vscode.window.showInformationMessage(
    'CCLS adds code completion and navigation for STM8 C code. Install it?', INSTALL, LATER, NEVER,
  );
  if (choice === INSTALL) {
    await vscode.commands.executeCommand('workbench.extensions.installExtension', CCLS);
  } else if (choice === NEVER) {
    await context.globalState.update(DISMISSED, true);
  }
}

module.exports = { offerCcls, CCLS, DISMISSED };
