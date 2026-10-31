# Releasing the extension

The extension is published on two marketplaces: Open VSX (VSCodium, Eclipse Theia, ...) by
`python3 .make/vscode/release.py`, and the Visual Studio Marketplace (VS Code) by hand.

## One-time setup

### Microsoft Visual Studio Marketplace

1. Sign in at <https://marketplace.visualstudio.com/manage> (Azure DevOps account) and create the
   publisher `spseol`.
2. Nothing else is needed: the VSIX is uploaded by hand (see below). The first upload uses
   "New extension" > "Visual Studio Code"; later versions use `...` > "Update" on the extension.

### Open VSX

1. Log in at <https://open-vsx.org> with GitHub.
2. Link an Eclipse account that uses the same GitHub username and sign the Publisher Agreement
   (<https://open-vsx.org/user-settings/profile>).
3. Create a token at Settings > Access Tokens.
4. Create the namespace once. Give the token through the environment, not through `-p TOKEN`
   (a command-line argument is visible to every user in `ps` and stays in the shell history):

   ```bash
   read -rs OVSX_PAT && export OVSX_PAT   # paste the token, nothing is echoed
   npx --yes ovsx@1.3.0 create-namespace spseol   # use the version of OVSX_VERSION in release.py
   unset OVSX_PAT
   ```

5. Claim ownership of the namespace so that the extension is not shown as unverified: follow the
   namespace-ownership instructions linked from
   <https://github.com/eclipse/openvsx/wiki/Publishing-Extensions>.
6. Store the token so that the release script finds it, either

   ```bash
   mkdir -p ~/.config/stm8-toolchain
   install -m 600 /dev/null ~/.config/stm8-toolchain/ovsx-token
   # paste the token into that file (a single line)
   ```

   or `export OVSX_PAT=...` for the shell that runs the release (it wins over the file).
   Keep the file at `chmod 600`. The script never prints the token, never puts it on a command line
   and never writes it into the repository.

The release script calls the pinned `ovsx@<OVSX_VERSION>` (constant in `release.py`) with
`npx --yes`, because the token is handed to that program. To move to a newer one: look up the
version with `npm view ovsx version`, read the ovsx changelog for breaking changes, edit
`OVSX_VERSION` in `.make/vscode/release.py`, and try `python3 .make/vscode/release.py --dry-run` (the dry run
does not call ovsx, so also check `npx --yes ovsx@NEW --version`).

## Releasing

1. Bump `version` in `.make/vscode/package.json` and add a heading with the version and the date
   to `.make/vscode/CHANGELOG.md`.
2. Commit and merge to `main`.
3. `python3 .make/vscode/release.py`
4. Upload `.make/vscode/stm8-toolchain.vsix` to Microsoft by hand: the script opens
   <https://marketplace.visualstudio.com/manage/publishers/spseol>; there choose the extension,
   then `...` > Update, and select the file (the first time: "New extension" > "Visual Studio Code").

`python3 .make/vscode/release.py --dry-run` does everything up to and including packing the VSIX (checks,
tests, `pack.py`) but publishes, tags and pushes nothing; it needs no token.

## What the script checks

In this order, stopping at the first problem:

1. The working tree is clean, the branch is `main`, the remotes `origin` and `github` exist and
   `main` is not behind `origin/main` (after `git fetch origin`).
2. The tag `vscode-v<version>` (version from `package.json`) does not exist yet.
3. A token is available (`OVSX_PAT` or `~/.config/stm8-toolchain/ovsx-token`); not needed for a dry run.
4. `python -m pytest .make/vscode` (the interpreter that runs the script) and `node --test .make/vscode/test/*.test.js` pass.
5. The VSIX is packed to `.make/vscode/stm8-toolchain.vsix`. A dry run ends here.
6. `npx ovsx publish` uploads the VSIX to Open VSX. The token reaches it only through the
   environment variable `OVSX_PAT`. When this fails, no tag is created.
7. The annotated tag `vscode-v<version>` is created and `main` plus the tag are pushed to `origin`
   and `github`. When a push fails, the script says which remote and prints the command to retry;
   the extension is already published at that point, so do not release again.
8. The path of the VSIX is printed and the Marketplace page is opened (a failure of `xdg-open` is
   only a warning).

## Limits of the checks

- The tag check is local only. A version that is already on Open VSX but has no local tag shows up
  as a failure of `ovsx publish` (nothing is tagged or pushed then).
- Only `origin` is fetched and compared with `main`. A diverged `github/main` shows up as a failed
  push after the publish; the script then prints the command to retry, and you fix the divergence
  by hand.

## Personal access tokens are being retired

Microsoft retires Azure DevOps personal access tokens on 2026-12-01, so `vsce publish` with a PAT
will stop working and the script does not try it. Afterwards the Marketplace gets the extension
only by the manual upload above, or via GitHub Actions with Trusted Publishing. That is not set up
here.
