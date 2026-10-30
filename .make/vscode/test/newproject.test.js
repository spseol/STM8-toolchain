'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFile, execFileSync } = require('node:child_process');
const { promisify } = require('node:util');
const { ToolchainError } = require('../src/project');
const { createProject, validateName, renderReadme, parsePruneList } = require('../src/newproject');

const real = promisify(execFile);
const MEDIA = path.join(__dirname, '..', 'media');
const IDENTITY = {
  GIT_AUTHOR_NAME: 'Test', GIT_AUTHOR_EMAIL: 'test@example.org', GIT_COMMITTER_NAME: 'Test', GIT_COMMITTER_EMAIL: 'test@example.org',
};
const ISOLATED = { GIT_CONFIG_GLOBAL: '/dev/null', GIT_CONFIG_SYSTEM: '/dev/null' };

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'stm8-newproject-'));
const git = (cwd, ...args) => execFileSync('git', args, { cwd, encoding: 'utf8', env: { ...process.env, ...IDENTITY } }).trim();

/** A "toolchain" repository on main with a Makefile, a README and .make/x. */
function toolchain() {
  const dir = tmp();
  git(dir, 'init', '-q', '-b', 'main');
  fs.mkdirSync(path.join(dir, '.make'));
  fs.writeFileSync(path.join(dir, 'Makefile'), 'all:\n');
  fs.writeFileSync(path.join(dir, 'README.md'), '# Original toolchain readme\n');
  fs.writeFileSync(path.join(dir, '.make', 'x'), 'x\n');
  git(dir, 'add', '.');
  git(dir, 'commit', '-q', '-m', 'toolchain');
  return dir;
}

/**
 * Real git, but `make` is replaced (it would need the SPL). `env` replaces the environment of every
 * call; `makes` collects the make calls; `makeError` makes them fail.
 */
function exec({ env, makeError } = {}) {
  const makes = [];
  const fn = async (cmd, args, options = {}) => {
    if (cmd === 'make') {
      makes.push({ args, cwd: options.cwd });
      if (makeError) throw makeError;
      return { stdout: '', stderr: '' };
    }
    return real(cmd, args, { ...options, env: env || { ...process.env, ...IDENTITY, ...options.env } });
  };
  fn.makes = makes;
  return fn;
}

test('creates_the_project_like_stm8newproject', async () => {
  const remote = toolchain();
  const parent = tmp();
  const run = exec();
  const { dir, warnings } = await createProject({ url: `file://${remote}`, parent, name: 'Žák Novák 1', mediaDir: MEDIA, exec: run });

  assert.strictEqual(dir, path.join(parent, 'Žák Novák 1'));
  assert.deepStrictEqual(warnings, []);
  assert.strictEqual(git(dir, 'rev-parse', '--abbrev-ref', 'HEAD'), 'main');
  assert.deepStrictEqual(git(dir, 'for-each-ref', '--format=%(refname)', 'refs/heads').split('\n').sort(), ['refs/heads/main', 'refs/heads/upstream']);
  assert.strictEqual(git(dir, 'remote'), 'upstream');
  assert.strictEqual(git(dir, 'rev-list', '--count', 'main'), '1');
  assert.strictEqual(git(dir, 'log', '--format=%s', 'main'), 'Initial commit');
  assert.deepStrictEqual(run.makes, [{ args: ['compile_commands.json'], cwd: dir }]);

  assert.strictEqual(fs.readFileSync(path.join(dir, 'README.origin.md'), 'utf8'), '# Original toolchain readme\n');
  const readme = fs.readFileSync(path.join(dir, 'README.md'), 'utf8');
  assert.ok(readme.startsWith('# Žák Novák 1\n'), readme.slice(0, 40));
  assert.match(readme, /Schéma zapojení/);
  assert.ok(!readme.includes('{{TITLE}}'));
  assert.ok(fs.readFileSync(path.join(dir, 'docs', 'schema.png')).equals(fs.readFileSync(path.join(MEDIA, 'schema.png'))));
  assert.ok(fs.existsSync(path.join(dir, 'Makefile')));
  assert.strictEqual(git(dir, 'status', '--porcelain'), '');
  // the toolchain history stays reachable on the upstream branch
  assert.strictEqual(git(dir, 'log', '--format=%s', 'upstream'), 'toolchain');
});

test('lowercase_name_gets_a_capital_in_the_title_only', async () => {
  const remote = toolchain();
  const parent = tmp();
  const { dir } = await createProject({ url: `file://${remote}`, parent, name: '  lab 1 ', mediaDir: MEDIA, exec: exec() });
  assert.strictEqual(path.basename(dir), 'lab 1');
  assert.ok(fs.readFileSync(path.join(dir, 'README.md'), 'utf8').startsWith('# Lab 1\n'));
});

test('failing_make_is_a_warning_and_the_project_is_finished', async () => {
  const remote = toolchain();
  const parent = tmp();
  const makeError = Object.assign(new Error('make: spawn make ENOENT'), { code: 'ENOENT', stderr: '' });
  const { dir, warnings } = await createProject({ url: `file://${remote}`, parent, name: 'p', mediaDir: MEDIA, exec: exec({ makeError }) });
  assert.strictEqual(warnings.length, 1);
  assert.match(warnings[0], /compile_commands\.json was not generated \(make failed: .*ENOENT.*\); run "make compile_commands\.json" later/);
  assert.strictEqual(git(dir, 'rev-list', '--count', 'main'), '1');
});

test('missing_git_identity_is_a_warning_and_the_files_stay', async () => {
  const remote = toolchain();
  const parent = tmp();
  const home = tmp();
  const env = {
    PATH: process.env.PATH, HOME: home, ...ISOLATED, GIT_CONFIG_COUNT: '1', GIT_CONFIG_KEY_0: 'user.useConfigOnly', GIT_CONFIG_VALUE_0: 'true',
  };
  // cloning a local repository does not need an identity, committing does
  const { dir, warnings } = await createProject({ url: `file://${remote}`, parent, name: 'p', mediaDir: MEDIA, exec: exec({ env }) });
  assert.strictEqual(warnings.length, 1);
  assert.match(warnings[0], /user\.name/);
  assert.match(warnings[0], /user\.email/);
  assert.match(warnings[0], /git config/);
  assert.ok(fs.existsSync(path.join(dir, 'README.md')));
  assert.ok(fs.existsSync(path.join(dir, 'docs', 'schema.png')));
  assert.throws(() => git(dir, 'rev-parse', '--verify', 'HEAD'), /./); // no commit on the new main
});

test('clone_failure_is_a_toolchain_error_with_the_url', async () => {
  const parent = tmp();
  const url = `file://${path.join(tmp(), 'does-not-exist')}`;
  await assert.rejects(
    createProject({ url, parent, name: 'p', mediaDir: MEDIA, exec: exec() }),
    (error) => error instanceof ToolchainError && error.message.includes(url) && error.message.startsWith('Cannot download the toolchain from'),
  );
  assert.deepStrictEqual(fs.readdirSync(parent), []);
});

test('a_step_after_the_clone_that_throws_is_reported_with_its_name_and_nothing_is_removed', async () => {
  const remote = toolchain();
  const parent = tmp();
  const real = exec();
  const broken = async (cmd, args, options) => {
    if (cmd === 'git' && args[0] === 'checkout') throw new Error('boom');
    return real(cmd, args, options);
  };
  await assert.rejects(
    createProject({ url: `file://${remote}`, parent, name: 'p', mediaDir: MEDIA, exec: broken }),
    (error) => error instanceof ToolchainError && /git checkout --orphan main/.test(error.message) && /boom/.test(error.message),
  );
  assert.ok(fs.existsSync(path.join(parent, 'p', 'Makefile')));
});

test('a_name_that_escapes_the_parent_is_rejected_and_nothing_is_created', async () => {
  const remote = toolchain();
  const base = tmp();
  const parent = path.join(base, 'parent');
  fs.mkdirSync(parent);
  for (const name of ['../x', '..', 'a/b', 'a\\b']) {
    await assert.rejects(
      createProject({ url: `file://${remote}`, parent, name, mediaDir: MEDIA, exec: exec() }),
      (error) => error instanceof ToolchainError,
      name,
    );
  }
  assert.deepStrictEqual(fs.readdirSync(base), ['parent']);
  assert.deepStrictEqual(fs.readdirSync(parent), []);
});

test('existing_directory_is_rejected', async () => {
  const remote = toolchain();
  const parent = tmp();
  fs.mkdirSync(path.join(parent, 'p'));
  await assert.rejects(createProject({ url: `file://${remote}`, parent, name: 'p', mediaDir: MEDIA, exec: exec() }), /already exists/);
});

test('validateName', () => {
  const parent = tmp();
  fs.mkdirSync(path.join(parent, 'taken'));
  for (const bad of ['', '   ', 'a/b', 'a\\b', '.x', '.', '..', 'taken', ' taken ', 'a\u0000b', 'a\nb']) {
    assert.strictEqual(typeof validateName(bad, parent), 'string', JSON.stringify(bad));
    assert.ok(validateName(bad, parent).length > 0);
  }
  assert.match(validateName('taken', parent), /already exists/);
  for (const good of ['lab 1', 'Žák', 'new-stm8-project', 'a.b']) {
    assert.strictEqual(validateName(good, parent), null, good);
  }
});

test('renderReadme', () => {
  assert.strictEqual(renderReadme('# {{TITLE}}\n\n{{TITLE}}', 'lab 1'), '# Lab 1\n\nLab 1');
  assert.strictEqual(renderReadme('# {{TITLE}}', ' Žák Novák 1 '), '# Žák Novák 1');
  assert.strictEqual(renderReadme('# {{TITLE}}', 'žák'), '# Žák');
  assert.strictEqual(renderReadme('# {{TITLE}}', '$&x'), '# $&x'); // no replace() patterns
});

// --- pruning dev-only files (.make/prune.txt) ---------------------------------------------

/**
 * A toolchain with a prune list. `victims` is a folder outside of every project; the list names
 * a file in it by an absolute path and `../sentinel.txt` (the folder of the new project's parent).
 */
function prunedToolchain(victims, { list } = {}) {
  const dir = toolchain();
  const put = (name, text = `${name}\n`) => {
    fs.mkdirSync(path.dirname(path.join(dir, name)), { recursive: true });
    fs.writeFileSync(path.join(dir, name), text);
  };
  put('.make/vscode/test/a.test.js');
  put('.make/vscode/test/sub/b.js');
  put('.make/vscode/release.py');
  put('.make/vscode/pack.py');
  put('.make/vscode/package.json');
  put('.make/vscode/src/newproject.js');
  put('CLAUDE.md');
  put('inc/main.h');
  put('lib/test/keep.c');
  put('.make/prune.txt', list || [
    '# dev-only files',
    '',
    '   ',
    '.make/vscode/test',
    '.make/vscode/release.py',
    '.make/vscode/not-there.md',
    '../sentinel.txt',
    path.join(victims, 'abs.txt'),
    '.make/vscode/test/../../../CLAUDE.md',
    '.git',
    '.',
    '',
  ].join('\n'));
  git(dir, 'add', '.');
  git(dir, 'commit', '-q', '-m', 'dev files');
  return dir;
}

const files = (dir, ref) => git(dir, 'ls-tree', '-r', '--name-only', ref).split('\n');

test('prunes_the_files_listed_in_prune_txt_before_the_first_commit', async () => {
  const victims = tmp();
  fs.writeFileSync(path.join(victims, 'abs.txt'), 'must survive\n');
  const remote = prunedToolchain(victims);
  const parent = tmp();
  fs.writeFileSync(path.join(parent, 'sentinel.txt'), 'must survive\n');
  const { dir, warnings } = await createProject({ url: `file://${remote}`, parent, name: 'p', mediaDir: MEDIA, exec: exec() });

  assert.deepStrictEqual(warnings, []);
  for (const gone of ['.make/vscode/test', '.make/vscode/release.py']) {
    assert.ok(!fs.existsSync(path.join(dir, gone)), gone);
  }
  const onMain = files(dir, 'main');
  assert.ok(!onMain.some((name) => name.startsWith('.make/vscode/test/') || name === '.make/vscode/release.py'), onMain.join(' '));
  for (const kept of ['.make/prune.txt', '.make/vscode/pack.py', '.make/vscode/package.json', '.make/vscode/src/newproject.js',
    'CLAUDE.md', 'inc/main.h', 'lib/test/keep.c', '.make/x', 'Makefile']) {
    assert.ok(onMain.includes(kept), kept);
    assert.ok(fs.existsSync(path.join(dir, kept)), kept);
  }
  // the toolchain history on upstream is untouched
  const onUpstream = files(dir, 'upstream');
  assert.ok(onUpstream.includes('.make/vscode/test/a.test.js'));
  assert.ok(onUpstream.includes('.make/vscode/test/sub/b.js'));
  assert.ok(onUpstream.includes('.make/vscode/release.py'));
  assert.strictEqual(git(dir, 'rev-list', '--count', 'main'), '1');
  assert.strictEqual(git(dir, 'status', '--porcelain'), '');
  // unsafe entries (absolute, `..`, .git, .) deleted nothing
  assert.strictEqual(fs.readFileSync(path.join(parent, 'sentinel.txt'), 'utf8'), 'must survive\n');
  assert.strictEqual(fs.readFileSync(path.join(victims, 'abs.txt'), 'utf8'), 'must survive\n');
  assert.ok(fs.existsSync(path.join(dir, '.git')));
});

test('without_prune_txt_nothing_is_pruned', async () => {
  const remote = prunedToolchain(tmp());
  git(remote, 'rm', '-q', '.make/prune.txt');
  git(remote, 'commit', '-q', '-m', 'no list');
  const { dir, warnings } = await createProject({ url: `file://${remote}`, parent: tmp(), name: 'p', mediaDir: MEDIA, exec: exec() });
  assert.deepStrictEqual(warnings, []);
  assert.ok(files(dir, 'main').includes('.make/vscode/test/a.test.js'));
  assert.strictEqual(git(dir, 'status', '--porcelain'), '');
});

test('an_entry_through_a_symlink_deletes_nothing_outside_the_project', async () => {
  const victims = tmp();
  fs.writeFileSync(path.join(victims, 'abs.txt'), 'must survive\n');
  const remote = prunedToolchain(victims, { list: '.make/link/abs.txt\n.make/vscode/release.py\n' });
  fs.symlinkSync(victims, path.join(remote, '.make', 'link'));
  git(remote, 'add', '.');
  git(remote, 'commit', '-q', '-m', 'link');
  const { dir } = await createProject({ url: `file://${remote}`, parent: tmp(), name: 'p', mediaDir: MEDIA, exec: exec() });
  assert.strictEqual(fs.readFileSync(path.join(victims, 'abs.txt'), 'utf8'), 'must survive\n');
  assert.ok(!fs.existsSync(path.join(dir, '.make', 'vscode', 'release.py'))); // the safe entry still works
  assert.strictEqual(git(dir, 'rev-list', '--count', 'main'), '1');
});

test('a_failing_prune_is_a_warning_and_the_project_is_finished', async () => {
  const remote = prunedToolchain(tmp());
  const real = exec();
  const broken = async (cmd, args, options) => {
    if (cmd === 'git' && args.includes('rm')) throw new Error('boom');
    return real(cmd, args, options);
  };
  const { dir, warnings } = await createProject({ url: `file://${remote}`, parent: tmp(), name: 'p', mediaDir: MEDIA, exec: broken });
  assert.ok(warnings.length >= 1);
  assert.match(warnings.join('\n'), /\.make\/vscode\/test/);
  assert.match(warnings.join('\n'), /boom/);
  assert.strictEqual(git(dir, 'rev-list', '--count', 'main'), '1');
  assert.ok(fs.existsSync(path.join(dir, 'README.md')));
});

test('parsePruneList', () => {
  const text = [
    '# comment', '', '  ', 'a/b', ' c/d/ ', './e', 'f//g', '/abs', '\\win', 'C:/x', '../up', 'a/../b', '..', '.', '.git', '.git/hooks',
    '#.make/hidden', 'a b/čau', 'dup', 'dup', '',
  ].join('\r\n');
  assert.deepStrictEqual(parsePruneList(text), ['a/b', 'c/d', 'e', 'f/g', 'a b/čau', 'dup']);
  assert.deepStrictEqual(parsePruneList(''), []);
  // .git in any spelling a case-insensitive or Windows file system maps to it, and dot-only segments
  assert.deepStrictEqual(parsePruneList(['.GIT', '.Git/hooks', '.git.', '.git ', '.git. .', '...', 'a/.../b', 'a/.. /b', 'a/.git', 'a/.gitignore', '.gitignore'].join('\n')),
    ['a/.git', 'a/.gitignore', '.gitignore']);
});

test('a_prune_entry_naming_dot_git_in_any_case_leaves_the_repository_alone', async () => {
  const remote = prunedToolchain(tmp(), { list: '.GIT\n.git.\n.Git/hooks\n.make/vscode/release.py\n' });
  const { dir, warnings } = await createProject({ url: `file://${remote}`, parent: tmp(), name: 'p', mediaDir: MEDIA, exec: exec() });
  assert.deepStrictEqual(warnings, []);
  assert.ok(fs.existsSync(path.join(dir, '.git', 'HEAD')));
  assert.strictEqual(git(dir, 'rev-list', '--count', 'main'), '1');
  assert.ok(!fs.existsSync(path.join(dir, '.make', 'vscode', 'release.py')));
});
