# Targets for the VS Code extension (.make/vscode/).
# Included at the end of the Makefile, so all its variables are defined.

.PHONY: dap-info debug-files

# paths and the OpenOCD command as one JSON line; builds nothing
dap-info:
	@$(PYTHON) .make/vscode/dap_info.py --device '$(DEVICE)' --device-flash '$(DEVICE_FLASH)' \
		--elf '$(TARGET_ELF)' --sfr '$(SFR_ELF)' --openocd '$(OPENOCD)' \
		--log '$(OUTPUT_DIR_ELF)/openocd.log'

# what F5 needs: the program with debug info and the peripheral registers (SFR) for gdb
debug-files: $(TARGET_ELF) $(SFR_ELF)

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
