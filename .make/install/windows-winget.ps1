# The same installer as windows.ps1, but with winget instead of Chocolatey.
#
#   irm https://raw.githubusercontent.com/spseol/STM8-toolchain/main/.make/install/windows-winget.ps1 | iex
#
# The whole logic is in windows.ps1; this file only chooses the package manager.
if (-not $STM8_BASE) { $STM8_BASE = 'https://raw.githubusercontent.com/spseol/STM8-toolchain/main/.make/install' }
$STM8_PM = 'winget'
irm "$STM8_BASE/windows.ps1" | iex
