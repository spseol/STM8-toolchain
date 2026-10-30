# Releasing the extension

The extension is published on two marketplaces: Open VSX (VSCodium, Eclipse Theia, ...) by
`make vscode-release`, and the Visual Studio Marketplace (VS Code) by hand.

## One-time setup

### Microsoft Visual Studio Marketplace

1. Sign in at <https://marketplace.visualstudio.com/manage> (Azure DevOps account) and create the
   publisher `spseol`.
2. Nothing else is needed: the VSIX is uploaded by hand (see below).

### Open VSX

1. Log in at <https://open-vsx.org> with GitHub.
2. Link an Eclipse account that uses the same GitHub username and sign the Publisher Agreement
   (<https://open-vsx.org/user-settings/profile>).
3. Create a token at Settings > Access Tokens.
4. Create the namespace once: `npx ovsx create-namespace spseol -p TOKEN`.
5. Ask for verification of the namespace (the claim button on the namespace page), otherwise the
   extension is shown as unverified.
6. Store the token so that the release script finds it, either

   ```bash
   mkdir -p ~/.config/stm8-toolchain
   install -m 600 /dev/null ~/.config/stm8-toolchain/ovsx-token
   # paste the token into that file (a single line)
   ```

   or `export OVSX_PAT=...` for the shell that runs the release (it wins over the file).
   Keep the file at `chmod 600`. The script never prints the token, never puts it on a command line
   and never writes it into the repository.

## Releasing

1. Bump `version` in `.make/vscode/package.json` and add a heading with the version and the date
   to `.make/vscode/CHANGELOG.md`.
2. Commit and merge to `main`.
3. `make vscode-release`
4. Upload `.make/vscode/stm8-toolchain.vsix` to Microsoft by hand: the script opens
   <https://marketplace.visualstudio.com/manage/publishers/spseol>; there choose the extension,
   then `...` > Update, and select the file.

`make vscode-release DRY_RUN=1` does everything up to and including packing the VSIX (checks,
tests, `pack.py`) but publishes, tags and pushes nothing; it needs no token.

## What the script checks

In this order, stopping at the first problem:

1. The working tree is clean, the branch is `main`, the remotes `origin` and `github` exist and
   `main` is not behind `origin/main` (after `git fetch origin`).
2. The tag `vscode-v<version>` (version from `package.json`) does not exist yet.
3. A token is available (`OVSX_PAT` or `~/.config/stm8-toolchain/ovsx-token`); not needed for a dry run.
4. `python3 -m pytest .make/vscode` and `node --test .make/vscode/test/*.test.js` pass.
5. The VSIX is packed to `.make/vscode/stm8-toolchain.vsix`. A dry run ends here.
6. `npx ovsx publish` uploads the VSIX to Open VSX. The token reaches it only through the
   environment variable `OVSX_PAT`. When this fails, no tag is created.
7. The annotated tag `vscode-v<version>` is created and `main` plus the tag are pushed to `origin`
   and `github`. When a push fails, the script says which remote and prints the command to retry;
   the extension is already published at that point, so do not release again.
8. The path of the VSIX is printed and the Marketplace page is opened (a failure of `xdg-open` is
   only a warning).

## Personal access tokens are being retired

Microsoft retires Azure DevOps personal access tokens on 2026-12-01, so `vsce publish` with a PAT
will stop working and the script does not try it. Afterwards the Marketplace gets the extension
only by the manual upload above, or via GitHub Actions with Trusted Publishing. That is not set up
here.
