'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { registerBuildTask, buildTask } = require('../src/tasks');

// A hand-written fake of the parts of `vscode` that tasks.js uses.
function fakeVscode(folders) {
  const seen = {};
  class Task {
    constructor(definition, scope, name, source, execution, problemMatchers) {
      Object.assign(this, { definition, scope, name, source, execution, problemMatchers });
    }
  }
  class ShellExecution {
    constructor(commandLine, options) { this.commandLine = commandLine; this.options = options; }
  }
  const vscode = {
    Task,
    ShellExecution,
    TaskGroup: { Build: { id: 'build' } },
    TaskRevealKind: { Silent: 3 },
    TaskPanelKind: { Shared: 1 },
    tasks: {
      registerTaskProvider: (type, provider) => {
        seen.type = type;
        seen.provider = provider;
        return { dispose() { seen.disposed = true; } };
      },
    },
    workspace: { workspaceFolders: folders },
  };
  return { vscode, seen };
}

const folderA = { uri: { fsPath: '/a' }, name: 'a', index: 0 };
const folderB = { uri: { fsPath: '/b' }, name: 'b', index: 1 };

test('registers_a_provider_for_type_stm8_and_returns_its_disposable', () => {
  const { vscode, seen } = fakeVscode([folderA]);
  const disposable = registerBuildTask(vscode);
  assert.strictEqual(seen.type, 'stm8');
  disposable.dispose();
  assert.ok(seen.disposed);
});

test('provideTasks_returns_one_build_task_per_workspace_folder', () => {
  const { vscode, seen } = fakeVscode([folderA, folderB]);
  registerBuildTask(vscode);
  const tasks = seen.provider.provideTasks();
  assert.strictEqual(tasks.length, 2);
  tasks.forEach((task, i) => {
    const folder = [folderA, folderB][i];
    assert.deepStrictEqual(task.definition, { type: 'stm8' });
    assert.strictEqual(task.scope, folder);
    assert.strictEqual(task.name, 'build'); // VS Code labels it "stm8: build" (source: name)
    assert.strictEqual(task.source, 'stm8');
    assert.strictEqual(task.execution.commandLine, 'make debug-files');
    assert.deepStrictEqual(task.execution.options, { cwd: folder.uri.fsPath });
    assert.deepStrictEqual(task.problemMatchers, ['$sdcc']);
    assert.strictEqual(task.group, vscode.TaskGroup.Build);
    assert.deepStrictEqual(task.presentationOptions, { reveal: 3, panel: 1 });
  });
});

test('provideTasks_without_workspace_folders_returns_nothing', () => {
  for (const folders of [undefined, []]) {
    const { vscode, seen } = fakeVscode(folders);
    registerBuildTask(vscode);
    assert.deepStrictEqual(seen.provider.provideTasks(), []);
  }
});

test('resolveTask_returns_the_task_for_its_own_folder', () => {
  const { vscode, seen } = fakeVscode([folderA, folderB]);
  registerBuildTask(vscode);
  const resolved = seen.provider.resolveTask({ definition: { type: 'stm8' }, scope: folderB });
  assert.strictEqual(resolved.scope, folderB);
  assert.deepStrictEqual(resolved.definition, { type: 'stm8' });
  assert.strictEqual(resolved.execution.options.cwd, '/b');
});

test('resolveTask_ignores_other_types_and_non_folder_scopes', () => {
  const { vscode, seen } = fakeVscode([folderA]);
  registerBuildTask(vscode);
  assert.strictEqual(seen.provider.resolveTask({ definition: { type: 'shell' }, scope: folderA }), undefined);
  assert.strictEqual(seen.provider.resolveTask({ definition: { type: 'stm8' }, scope: 1 }), undefined); // vscode.TaskScope.Global
});

test('buildTask_is_exported', () => {
  const { vscode } = fakeVscode([]);
  assert.strictEqual(buildTask(vscode, folderA).name, 'build');
});
