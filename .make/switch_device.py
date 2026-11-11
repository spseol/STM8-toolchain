#!/usr/bin/env python3
# Soubor:  set_device.py
# Datum:   09.03.2024 19:02
# Autor:   Marek Nožka, nozka <@t> spseol <d.t> cz
# Autor:   Marek Nožka, marek <@t> tlapicka <d.t> net
# Licence: GNU/GPL
############################################################################
import sys
from devices import available

try:
    from pick import pick
except ImportError:
    from winpick import pick


############################################################################


DEVICES = available()  # only what ../SPLSPL/mk can build
if not DEVICES:
    sys.exit("No chip can be selected: ../SPLSPL/mk has no usable file.")

femilly, index = pick(list(DEVICES), "Select the family:")
device, index = pick(list(DEVICES[femilly]), "Select the chip:")

with open(sys.argv[1], "w") as f:
    f.write(device.lower())
