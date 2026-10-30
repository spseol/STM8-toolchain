'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const { ToolchainError } = require('./project');

const run = promisify(execFile);
const MAX_BUFFER = 16 * 1024 * 1024;
const COMMIT_MESSAGE = 'Initial commit';

const message = (error) => `${error.stderr || ''}`.trim() || `${error.message || error}`.trim();

/** Why NAME cannot be a new project folder in PARENT, or null. */
function validateName(name, parent) {
  const trimmed = String(name || '').trim();
  if (!trimmed) return 'Enter a name for the project.';
  if (/[/\\]/.test(trimmed)) return 'The name must not contain / or \\ (it is the name of one folder).';
  if (/[\u0000-\u001f\u007f]/.test(trimmed)) return 'The name must not contain control characters.';
  if (trimmed.startsWith('.')) return 'The name must not start with a dot.';
  const dir = path.join(parent, trimmed);
  let exists = true;
  try {
    fs.lstatSync(dir);
  } catch {
    exists = false;
  }
  return exists ? `${dir} already exists.` : null;
}

/** The README template with {{TITLE}} replaced by the project name with a capital first letter. */
function renderReadme(template, name) {
  const trimmed = String(name).trim();
  const title = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  return template.split('{{TITLE}}').join(title);
}

/**
 * Creates a project like the stm8newproject script: clones the toolchain, keeps its history on the
 * branch `upstream` (the remote is `upstream` as well, which is what Update Toolchain and the student's
 * `git pull upstream` expect), starts an orphan `main` with a project README and a schema image.
 * Everything is created in PARENT/NAME. A failed `make` or `git commit` is only a warning.
 */
async function createProject({ url, parent, name, mediaDir, exec = run }) {
  const title = String(name).trim();
  const problem = validateName(title, parent);
  if (problem) throw new ToolchainError(problem);
  const dir = path.join(parent, title);
  if (path.dirname(path.resolve(dir)) !== path.resolve(parent)) throw new ToolchainError(`${dir} is not directly inside ${parent}.`);

  const options = { maxBuffer: MAX_BUFFER, env: { ...process.env, GIT_TERMINAL_PROMPT: '0' } };
  try {
    // `--`: a url that starts with - is then a repository, never an option
    await exec('git', ['clone', '--', url, dir], options);
  } catch (error) {
    throw new ToolchainError(`Cannot download the toolchain from ${url}: ${message(error)}`);
  }

  const inDir = { ...options, cwd: dir };
  const step = async (what, action) => {
    try {
      return await action();
    } catch (error) {
      throw new ToolchainError(`Cannot create the project: "${what}" failed in ${dir}: ${message(error)}`);
    }
  };
  const git = (...args) => step(`git ${args.join(' ')}`, () => exec('git', args, inDir));
  const warnings = [];

  await git('branch', '-m', 'upstream');
  await git('remote', 'rename', 'origin', 'upstream');
  await git('checkout', '--orphan', 'main');
  try {
    await exec('make', ['compile_commands.json'], inDir);
  } catch (error) {
    warnings.push(`compile_commands.json was not generated (make failed: ${message(error)}); run "make compile_commands.json" later`);
  }

  await step('README.md and docs/schema.png', () => {
    fs.renameSync(path.join(dir, 'README.md'), path.join(dir, 'README.origin.md'));
    const template = fs.readFileSync(path.join(mediaDir, 'README.project.md'), 'utf8');
    fs.writeFileSync(path.join(dir, 'README.md'), renderReadme(template, title));
    fs.mkdirSync(path.join(dir, 'docs'), { recursive: true });
    fs.copyFileSync(path.join(mediaDir, 'schema.png'), path.join(dir, 'docs', 'schema.png'));
  });

  await git('add', '.');
  try {
    await exec('git', ['commit', '-m', COMMIT_MESSAGE], inDir);
  } catch (error) {
    warnings.push(
      `The project was created, but the first commit failed (${message(error).split('\n')[0]}). `
      + 'Set your identity (git config --global user.name "Your Name"; git config --global user.email "you@example.org") '
      + 'and commit in the project: git commit -m "Initial commit".',
    );
  }
  return { dir, warnings };
}

const CHOOSE = 'Choose another folder…';

/** The UI of `STM8: New Project…`: folder, name, progress, warnings, opening the folder. */
async function newProjectFlow(vscode, { createProject: create = createProject, context }) {
  const config = vscode.workspace.getConfiguration('stm8');
  const chooseFolder = async () => {
    const picked = await vscode.window.showOpenDialog({
      canSelectFolders: true,
      canSelectFiles: false,
      canSelectMany: false,
      openLabel: 'Use as projects folder',
      title: 'Folder for your STM8 projects (they share ../SPLSPL)',
    });
    if (!picked || picked.length === 0) return undefined;
    await config.update('projectsFolder', picked[0].fsPath, vscode.ConfigurationTarget.Global);
    return picked[0].fsPath;
  };

  let folder = config.get('projectsFolder');
  if (!folder) {
    folder = await chooseFolder();
  } else {
    const choice = await vscode.window.showQuickPick([{ label: `Create in ${folder}` }, { label: CHOOSE }], { placeHolder: 'Where should the new project be created?' });
    if (!choice) return;
    if (choice.label === CHOOSE) folder = await chooseFolder();
  }
  if (!folder) return;

  const name = await vscode.window.showInputBox({
    prompt: `Name of the new project (a folder in ${folder})`,
    placeHolder: 'new-stm8-project',
    validateInput: (text) => validateName(text, folder) || undefined,
  });
  if (name === undefined || !name.trim()) return;

  const url = config.get('toolchainUrl');
  const mediaDir = path.join(context.extensionPath, 'media');
  let created;
  try {
    created = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `Creating project ${name.trim()}…` },
      () => create({ url, parent: folder, name, mediaDir }),
    );
  } catch (error) {
    await vscode.window.showErrorMessage(error.message);
    return;
  }
  // the window may be replaced by the project below, so the warnings are read first
  if (created.warnings.length > 0) await vscode.window.showWarningMessage(created.warnings.join('\n\n'), { modal: true });
  const forceNewWindow = (vscode.workspace.workspaceFolders || []).length > 0;
  await vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(created.dir), { forceNewWindow });
}

module.exports = { validateName, renderReadme, createProject, newProjectFlow };
