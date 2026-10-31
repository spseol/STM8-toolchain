# Targets for the VS Code extension (.make/vscode/).
# Included at the end of the Makefile, so all its variables are defined.

.PHONY: dap-info debug-files

# paths and the OpenOCD command as one JSON line; builds nothing
dap-info:
	@$(PYTHON) .make/vscode/dap_info.py --device '$(DEVICE)' --device-flash '$(DEVICE_FLASH)' \
		--elf '$(TARGET_ELF)' --sfr '$(SFR_ELF)' --openocd '$(OPENOCD)' \
		--log '$(OUTPUT_DIR_ELF)/openocd.log'

# what F5 needs: the program with debug info and the peripheral registers (SFR) for gdb
ifeq ($(wildcard ../SPLSPL),)
# fresh project: make has read the Makefile without the SPL sources,
# so download SPL and start make again
debug-files:
	$(MAKE) --no-print-directory spl
	$(MAKE) --no-print-directory $(TARGET_ELF) $(SFR_ELF)
else
debug-files: $(TARGET_ELF) $(SFR_ELF)
endif

.PHONY: vscode

VSIX = .make/vscode/stm8-toolchain.vsix
IDES ?= code codium

# package the extension and install it into every VS Code / VSCodium found (once per computer)
vscode:
	$(PYTHON) .make/vscode/pack.py $(VSIX)
	@installed=0; \
	for ide in $(IDES); do \
		if command -v $$ide >/dev/null 2>&1; then $$ide --install-extension $(VSIX) --force && installed=1; fi; \
	done; \
	if [ $$installed = 0 ]; then \
		echo "None of '$(IDES)' found in PATH. Install $(VSIX) by hand: Extensions view > ... > Install from VSIX."; \
		exit 1; \
	fi

.PHONY: upgrade

STM8_TOOLCHAIN_URL ?= https://gitlab.com/spseol/mit-no/STM8S-toolchain.git
UPGRADE_ARGS ?=

# update .make/ and the Makefile from the toolchain repository, run by the fetched upgrade.py;
# the script goes through -c, so stdin stays free for its questions; -I keeps the
# project folder (a student's difflib.py, json.py, ...) out of sys.path
upgrade:
	git fetch '$(STM8_TOOLCHAIN_URL)' main
	@script=$$(git show FETCH_HEAD:.make/upgrade.py) || { \
		echo "The toolchain at $(STM8_TOOLCHAIN_URL) has no .make/upgrade.py, nothing was changed."; \
		exit 1; \
	}; \
	$(PYTHON) -I -c "$$script" FETCH_HEAD $(UPGRADE_ARGS)
