'use strict';
const fs = require('node:fs');
const os = require('node:os');
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
 * The entries of .make/prune.txt: one path relative to the project per line, `#` comments and blank
 * lines skipped. Never returned (the list comes from a downloaded repository): absolute paths,
 * backslashes, `..` segments (also `...`) and everything in .git (in any case, with trailing dots or spaces). Same rules as in stm8newproject and upgrade.py.
 */
function parsePruneList(text) {
  const entries = [];
  for (const raw of String(text).split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#') || line.includes('\\') || /^([/]|[A-Za-z]:)/.test(line)) continue;
    const parts = line.split('/').filter((part) => part && part !== '.');
    // a segment of dots and spaces is `..` on Windows, `.GIT` and `.git.` are .git on case-insensitive file systems
    if (parts.length === 0 || parts.some((part) => /^[. ]+$/.test(part)) || parts[0].replace(/[. ]+$/, '').toLowerCase() === '.git') continue;
    entries.push(parts.join('/'));
  }
  return [...new Set(entries)];
}

/**
 * Removes what .make/prune.txt lists (tests and developer scripts a student does not need) from the
 * working tree and the index of the fresh clone in DIR. No list, nothing to do. Returns warnings
 * for entries that could not be removed; an entry that leads outside of DIR through a symbolic link is one.
 */
async function pruneProject(dir, exec, options) {
  let text;
  try {
    text = fs.readFileSync(path.join(dir, '.make', 'prune.txt'), 'utf8');
  } catch {
    return [];
  }
  const warnings = [];
  const root = fs.realpathSync(dir);
  for (const entry of parsePruneList(text)) {
    const target = path.join(dir, ...entry.split('/'));
    try {
      let parent;
      try {
        parent = fs.realpathSync(path.dirname(target));
      } catch {
        continue; // the folder is not there, so neither is the entry
      }
      if (parent !== root && !parent.startsWith(root + path.sep)) throw new Error('it leads outside of the project through a symbolic link');
      // --literal-pathspecs: no globs; the index first, then whatever was untracked
      await exec('git', ['--literal-pathspecs', 'rm', '-r', '-f', '-q', '--ignore-unmatch', '--', entry], options);
      fs.rmSync(target, { recursive: true, force: true });
    } catch (error) {
      warnings.push(`${entry} was not removed from the new project (${message(error).split('\n')[0]}); delete it by hand if you do not need it.`);
    }
  }
  return warnings;
}

/**
 * Creates a project like the stm8newproject script: clones the toolchain, keeps its history on the
 * branch `upstream` (the remote is `upstream` as well, which is what Update Toolchain and the student's
 * `git pull upstream` expect), starts an orphan `main` with a project README and a schema image.
 * Files listed in .make/prune.txt (extension tests, release scripts) are removed first, so `main`
 * never has them. `upstream` keeps the full toolchain.
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
  const warnings = await pruneProject(dir, exec, inDir);

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

/** The setting stm8.projectsFolder as an absolute path (a leading ~ is the home folder), or null. */
function absoluteFolder(value) {
  const folder = /^~(?=$|[/\\])/.test(value) ? path.join(os.homedir(), value.slice(1)) : value;
  return path.isAbsolute(folder) ? folder : null;
}

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
  if (folder && !absoluteFolder(folder)) {
    await vscode.window.showWarningMessage(
      `The setting stm8.projectsFolder must be an absolute path (it is "${folder}"). Choose the folder for your projects.`,
    );
    folder = undefined;
  } else if (folder) {
    folder = absoluteFolder(folder);
  }
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

module.exports = { validateName, renderReadme, parsePruneList, createProject, newProjectFlow, absoluteFolder };
