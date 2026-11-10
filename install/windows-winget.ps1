# Experimental: the same installer as windows.ps1, but with winget instead of Chocolatey.
#
#   irm https://gitlab.com/spseol/mit-no/STM8S-toolchain/-/raw/main/install/windows-winget.ps1 | iex
#
# The whole logic is in windows.ps1; this file only chooses the package manager.
if (-not $STM8_BASE) { $STM8_BASE = 'https://gitlab.com/spseol/mit-no/STM8S-toolchain/-/raw/main/install' }
$STM8_PM = 'winget'
irm "$STM8_BASE/windows.ps1" | iex
