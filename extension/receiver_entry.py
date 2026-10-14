"""Launch the packaged companion in Python's isolated mode."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "receiver"))
from blindspot.cli import main

raise SystemExit(main())
