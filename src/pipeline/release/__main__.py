"""Run source-release preparation or packaging with ``python -m pipeline.release``."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
