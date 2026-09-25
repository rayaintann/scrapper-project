"""Entry point: `python -m orchestration.one_pass_enrichment [--dry-run | --report-only]`.

Dijalankan dari root project. Implementasinya ada di
`kol_orchestration/one_pass.py`; file ini hanya menyiapkan `sys.path` dengan pola
yang sama seperti `run_e2e_once.py` (root project + folder orchestration/).
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parent, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from kol_orchestration.one_pass import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
