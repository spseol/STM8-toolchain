'use strict';

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

/** Offers the build task in every workspace folder. Returns a Disposable. */
function registerBuildTask(vscode) {
  return vscode.tasks.registerTaskProvider('stm8', {
    provideTasks: () => (vscode.workspace.workspaceFolders || []).map((folder) => buildTask(vscode, folder)),
    // VS Code gives back a task from tasks.json ({ type: 'stm8' }); the result must keep its definition
    resolveTask: (task) => {
      const folder = task.scope;
      if (task.definition.type !== 'stm8' || !folder || !folder.uri) return undefined; // not a WorkspaceFolder scope
      return buildTask(vscode, folder);
    },
  });
}

module.exports = { registerBuildTask, buildTask };
