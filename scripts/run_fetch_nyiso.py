"""Run the NYISO/NOAA downloader with the package on sys.path (python -E -P ignores cwd and PYTHONPATH)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from revstress.data.fetch_nyiso import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
