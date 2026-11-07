"""Pack server/gate into one file (a Python zipapp): pack-gate.py SOURCE OUT"""

import os
import sys
import zipapp

source, out = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(out), exist_ok=True)
zipapp.create_archive(source, out, interpreter="/usr/bin/env python3",
                      filter=lambda p: "__pycache__" not in p.parts)
os.chmod(out, 0o644)
