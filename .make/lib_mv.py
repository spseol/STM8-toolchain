#!/usr/bin/env python3
import sys
import os
import glob

try:
    from pick import pick
except ImportError:
    from winpick import pick

lib_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
files = glob.glob(os.path.join(lib_dir, '*.c')) + glob.glob(os.path.join(lib_dir, '*.h'))
bases = sorted(set(os.path.splitext(os.path.basename(f))[0] for f in files))

if not bases:
    sys.exit(0)

selected = pick(bases, "Select libraries (Space = select, Enter = confirm):", multiselect=True)

with open(sys.argv[1], 'w', newline='\n') as f:
    for item, _ in selected:
        f.write(item + '\n')
