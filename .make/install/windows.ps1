# One-command installer of the STM8S toolchain tools for Windows 10/11 (x64).
#
#   irm https://gitlab.com/spseol/mit-no/STM8S-toolchain/-/raw/main/.make/install/windows.ps1 | iex
#
# Run it in PowerShell. It asks for administrator rights (UAC) once and installs:
#   * with Chocolatey (default; installed when missing) or with winget: git, make, python, openocd
#     [and vscodium, when neither VS Code nor VSCodium is found],
#   * SDCC (installer from SourceForge, into the default folder C:\Program Files\SDCC),
#   * stm8-gdb (STM8 binutils-gdb installer from GitLab, adds itself to PATH),
#   * ccls (optional, installer from GitLab),
#   * the VS Code / VSCodium extension.
# Not installed: the ST-Link driver and STVP (ST publishes them after registration; flashing
# works through OpenOCD without STVP).
#
# Both package managers work equally. To use winget instead of Chocolatey:
#   $STM8_PM = 'winget'; irm https://gitlab.com/spseol/mit-no/STM8S-toolchain/-/raw/main/.make/install/windows.ps1 | iex
#
# Safe to run again: what is installed already is skipped.
# A manual installation and details: https://chytrosti.marrek.cz/stm8install.html#windows

# --- settings (a variable set before running overrides the default) ---------------------
if (-not $STM8_PM)   { $STM8_PM   = 'choco' }   # 'choco' or 'winget'
if (-not $STM8_BASE) { $STM8_BASE = 'https://gitlab.com/spseol/mit-no/STM8S-toolchain/-/raw/main/.make/install' }
$SdccVersion  = '4.6.0'                         # 4.5.0 is broken for STM8
$SdccDir      = "$env:ProgramFiles\SDCC"       # Makefile-sdcc expects this exact folder
$GdbApi       = 'https://gitlab.com/api/v4/projects/spseol%2Fmit-no%2Fstm8-binutils-gdb/releases/permalink/latest'
$CclsApi      = 'https://gitlab.com/api/v4/projects/spseol%2Fmit-no%2Fccls/releases?per_page=1'
$ExtensionId  = 'spseol.stm8-toolchain'
$Blog         = 'https://chytrosti.marrek.cz/stm8install.html'
# winget package ids
$WingetIds    = @('Git.Git', 'ezwinports.make', 'Python.Python.3.12', 'xpack-dev-tools.openocd-xpack')
$WingetEditor = 'VSCodium.VSCodium'

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'      # Invoke-WebRequest is much faster without it
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Say($text)  { Write-Host "`n== $text" -ForegroundColor Cyan }
function Warn($text) { Write-Host "WARNING: $text" -ForegroundColor Yellow }

function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Test-Tool($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Invoke-Installer($file, $arguments) {
    $p = Start-Process -FilePath $file -ArgumentList $arguments -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "$file ended with exit code $($p.ExitCode)" }
}

# --- administrator rights: restart elevated, once -----------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Say 'Administrator rights are needed. Confirm the Windows (UAC) dialog.'
    $inner = "`$STM8_PM='$STM8_PM'; `$STM8_BASE='$STM8_BASE'; irm '$STM8_BASE/windows.ps1' | iex"
    Start-Process powershell -Verb RunAs -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $inner)
    return
}

try {
    # --- package manager -------------------------------------------------------------
    if ($STM8_PM -eq 'choco') {
        if (-not (Test-Tool 'choco')) {
            Say 'Installing Chocolatey'
            Set-ExecutionPolicy Bypass -Scope Process -Force
            Invoke-Expression ((New-Object Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
            Update-SessionPath
            $env:Path += ";$env:ALLUSERSPROFILE\chocolatey\bin"
        }
    } elseif ($STM8_PM -eq 'winget') {
        if (-not (Test-Tool 'winget')) { throw 'winget not found. Update "App Installer" in Microsoft Store, or use the default Chocolatey.' }
    } else {
        throw "Unknown `$STM8_PM '$STM8_PM' (use 'choco' or 'winget')."
    }

    # --- base tools ------------------------------------------------------------------
    $hasEditor = (Test-Tool 'code') -or (Test-Tool 'codium') -or
                 (Test-Path "$env:ProgramFiles\Microsoft VS Code\bin\code.cmd") -or
                 (Test-Path "$env:ProgramFiles\VSCodium\bin\codium.cmd") -or
                 (Test-Path "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code.cmd") -or
                 (Test-Path "$env:LOCALAPPDATA\Programs\VSCodium\bin\codium.cmd")

    Say "Installing git, make, python, openocd ($STM8_PM)"
    if ($STM8_PM -eq 'choco') {
        choco install -y git make python openocd
        if (-not $hasEditor) { Say 'Installing VSCodium'; choco install -y vscodium }
    } else {
        $ids = $WingetIds
        if (-not $hasEditor) { $ids = $ids + $WingetEditor }
        foreach ($id in $ids) {
            winget install -e --id $id --silent --accept-source-agreements --accept-package-agreements
            # 0x8A150061 = already installed, -1978335189 on some versions: not an error
            if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) { Warn "winget install $id ended with code $LASTEXITCODE" }
        }
    }
    Update-SessionPath

    $tmp = Join-Path $env:TEMP 'stm8-install'
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null

    # --- SDCC ------------------------------------------------------------------------
    $sdccExe = Join-Path $SdccDir 'bin\sdcc.exe'
    $sdccOk = $false
    if (Test-Path $sdccExe) {
        $v = (& $sdccExe -v 2>&1 | Select-Object -First 1)
        if ($v -notmatch ' 4\.5\.0 ') { $sdccOk = $true; Say "SDCC is installed already ($v), skipping" }
        else { Warn "SDCC 4.5.0 is broken for STM8, installing $SdccVersion over it" }
    }
    if (-not $sdccOk) {
        Say "Installing SDCC $SdccVersion"
        $file = Join-Path $tmp "sdcc-$SdccVersion-x64-setup.exe"
        # SourceForge gives the file itself only to non-browser clients
        Invoke-WebRequest -UseBasicParsing -UserAgent 'Wget/1.21' -OutFile $file `
            -Uri "https://sourceforge.net/projects/sdcc/files/sdcc-win64/$SdccVersion/sdcc-$SdccVersion-x64-setup.exe/download"
        Invoke-Installer $file '/S'
    }

    # --- stm8-gdb --------------------------------------------------------------------
    $needGdb = $true
    if (Test-Tool 'stm8-gdb') {
        $gv = (stm8-gdb --version 2>&1 | Select-Object -First 1)
        if ($gv -match '(\d+)\.\d+' -and [int]$Matches[1] -ge 15) { $needGdb = $false; Say "stm8-gdb is installed already ($gv), skipping" }
    }
    if ($needGdb) {
        Say 'Installing stm8-gdb'
        $rel = Invoke-RestMethod -Uri $GdbApi
        $asset = $rel.assets.links | Where-Object { $_.name -eq 'stm8-binutils-gdb-windows-x64-setup.exe' } | Select-Object -First 1
        if (-not $asset) { throw 'stm8-gdb installer not found in the latest release: https://gitlab.com/spseol/mit-no/stm8-binutils-gdb/-/releases' }
        $file = Join-Path $tmp $asset.name
        $url = if ($asset.direct_asset_url) { $asset.direct_asset_url } else { $asset.url }
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $file
        Invoke-Installer $file '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /ALLUSERS /TASKS=addpath'
        Update-SessionPath
    }

    # --- ccls (optional) -------------------------------------------------------------
    if (-not (Test-Tool 'ccls')) {
        Say 'Installing ccls (optional)'
        try {
            $rel = (Invoke-RestMethod -Uri $CclsApi)[0]
            $asset = $rel.assets.links | Where-Object { $_.name -like 'ccls-*-windows-x64-setup.exe' } | Select-Object -First 1
            if (-not $asset) { throw 'installer not found in the latest release' }
            $file = Join-Path $tmp $asset.name
            $url = if ($asset.direct_asset_url) { $asset.direct_asset_url } else { $asset.url }
            Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $file
            Invoke-Installer $file '/S'
            Update-SessionPath
            if (-not (Test-Tool 'ccls')) { Warn 'ccls installed but not in PATH. Add it in the installer by hand, or use the clangd extension instead.' }
        } catch {
            Warn "ccls was not installed: $($_.Exception.Message). It is optional (code completion); see $Blog#windows-ccls"
        }
    }

    # --- editor extension ------------------------------------------------------------
    $ideCandidates = @(
        @{ Name = 'code';   Paths = @("$env:ProgramFiles\Microsoft VS Code\bin\code.cmd", "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code.cmd") },
        @{ Name = 'codium'; Paths = @("$env:ProgramFiles\VSCodium\bin\codium.cmd", "$env:LOCALAPPDATA\Programs\VSCodium\bin\codium.cmd") }
    )
    $installedInto = 0
    foreach ($ide in $ideCandidates) {
        $cmd = $null
        if (Test-Tool $ide.Name) { $cmd = $ide.Name }
        else { $cmd = $ide.Paths | Where-Object { Test-Path $_ } | Select-Object -First 1 }
        if ($cmd) {
            Say "Installing the extension $ExtensionId into $($ide.Name)"
            & $cmd --install-extension $ExtensionId --force
            if ($LASTEXITCODE -eq 0) { $installedInto++ } else { Warn "installation into $($ide.Name) failed" }
        }
    }
    if ($installedInto -eq 0) { Warn "No editor found. Install VSCodium or VS Code and then the extension '$ExtensionId' from its Extensions view." }

    # --- check -----------------------------------------------------------------------
    Say 'Checking'
    foreach ($t in @('git', 'make', 'python', 'openocd', 'stm8-gdb')) {
        if (Test-Tool $t) { Write-Host "$t : OK" } else { Warn "$t not found in PATH (open a NEW terminal window and try again)" }
    }
    if (Test-Path $sdccExe) { Write-Host (& $sdccExe -v 2>&1 | Select-Object -First 1) } else { Warn "SDCC not found in $SdccDir" }
    if (Test-Tool 'stm8-gdb') {
        $py = (stm8-gdb -batch -ex 'python print(1)' 2>&1 | Select-Object -Last 1)
        if ($py -eq '1') { Write-Host 'stm8-gdb Python: OK' } else { Warn 'stm8-gdb has no Python support. The debugger will not work.' }
    }

    Say 'Done'
    Write-Host 'Close this window, start the editor again and run "STM8: New Project..." from the Command Palette.'
    Write-Host 'ST-Link driver: if the board is not found, install STSW-LINK009 from https://www.st.com/en/development-tools/stsw-link009.html'
    Write-Host "Details: $Blog"
} catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Manual installation: $Blog"
}
