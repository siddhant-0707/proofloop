"""Download NISAR granules from ASF using Earthdata credentials in ~/.netrc.

Uses curl because it handles the Earthdata OAuth redirect, cookies and
resuming interrupted transfers reliably.

    uv run python -m proofloop.nisar.download --max-priority 1
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from proofloop.nisar.manifest import GRANULES, Granule
from proofloop.paths import RAW_NISAR_DIR


def download(granule: Granule, dest_dir: Path) -> Path:
    dest = dest_dir / granule.filename
    if dest.exists() and dest.stat().st_size == granule.size_bytes:
        print(f"ok    {granule.filename}")
        return dest

    cookies = dest_dir / ".urs_cookies"
    print(f"get   {granule.filename} ({granule.size_bytes / 1e9:.2f} GB)")
    subprocess.run(
        [
            "curl",
            "--fail",
            "--location",
            "--netrc",
            "--cookie",
            str(cookies),
            "--cookie-jar",
            str(cookies),
            "--continue-at",
            "-",
            "--retry",
            "5",
            "--output",
            str(dest),
            granule.url,
        ],
        check=True,
    )
    size = dest.stat().st_size
    if size != granule.size_bytes:
        raise RuntimeError(f"{dest.name}: got {size} bytes, expected {granule.size_bytes}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-priority", type=int, default=2)
    args = parser.parse_args()

    if shutil.which("curl") is None:
        sys.exit("curl is required")
    if not (Path.home() / ".netrc").exists():
        sys.exit("~/.netrc with urs.earthdata.nasa.gov credentials is required")

    RAW_NISAR_DIR.mkdir(parents=True, exist_ok=True)
    for granule in sorted(GRANULES, key=lambda g: (g.priority, g.size_bytes)):
        if granule.priority <= args.max_priority:
            download(granule, RAW_NISAR_DIR)


if __name__ == "__main__":
    main()
