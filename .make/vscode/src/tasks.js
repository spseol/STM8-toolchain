'use strict';
const fs = require('node:fs');
const path = require('node:path');

const OWN_LABEL = /"label"\s*:\s*"stm8: build"/; // tasks.json is JSONC (comments), so no JSON.parse

/** True when FOLDER's .vscode/tasks.json defines the label `stm8: build` itself; a read error means no. */
function hasOwnBuildTask(folder) {
  try {
    return OWN_LABEL.test(fs.readFileSync(path.join(folder.uri.fsPath, '.vscode', 'tasks.json'), 'utf8'));
  } catch {
    return false;
  }
}

/**
 * The build task `stm8: build` that launch.json uses as preLaunchTask. VS Code labels a task
 * of an extension "<source>: <name>", so source 'stm8' and name 'build' make the label exactly
 * "stm8: build" - the same one the shell task in .vscode/tasks.json has.
 */
function buildTask(vscode, folder) {
  const task = new vscode.Task(
    { type: 'stm8' }, folder, 'build', 'stm8',
    new vscode.ShellExecution('make debug-files', { cwd: folder.uri.fsPath }),
    ['$sdcc'], // declared in package.json (contributes.problemMatchers)
  );
  task.group = vscode.TaskGroup.Build;
  task.presentationOptions = { reveal: vscode.TaskRevealKind.Silent, panel: vscode.TaskPanelKind.Shared };
  return task;
}

/**
 * Offers the build task in every workspace folder whose tasks.json does not define `stm8: build`
 * already (the toolchain ships one, two tasks with the same label would make F5 ask). Returns a Disposable.
 */
function registerBuildTask(vscode) {
  return vscode.tasks.registerTaskProvider('stm8', {
    provideTasks: () => (vscode.workspace.workspaceFolders || [])
      .filter((folder) => !hasOwnBuildTask(folder))
      .map((folder) => buildTask(vscode, folder)),
    // VS Code gives back a task from tasks.json ({ type: 'stm8' }); the result must keep its definition
    resolveTask: (task) => {
      const folder = task.scope;
      if (task.definition.type !== 'stm8' || !folder || !folder.uri) return undefined; // not a WorkspaceFolder scope
      return buildTask(vscode, folder);
    },
  });
}

module.exports = { registerBuildTask, buildTask };
