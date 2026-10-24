"""Read NISAR granules in place over HTTP range requests.

A GCOV granule is 5 to 7 GB, but the World needs a crop of a few hundred MB. h5py reads
any seekable file object, so a crop costs only the bytes of the chunks it touches.
"""

import io
import subprocess
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from collections.abc import Buffer
from pathlib import Path

from proofloop.nisar.manifest import Granule

BLOCK_BYTES = 4 << 20
CACHED_BLOCKS = 64
_ATTEMPTS = 4


def signed_url(granule: Granule, cookies: Path) -> str:
    """Follow the Earthdata login redirects (credentials in ~/.netrc) to the granule's
    pre-signed download URL, which needs no further authentication."""
    result = subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--netrc",
            "--cookie",
            str(cookies),
            "--cookie-jar",
            str(cookies),
            "--range",
            "0-0",
            "--output",
            "/dev/null",
            "--write-out",
            "%{url_effective}",
            granule.url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


class RemoteFile(io.RawIOBase):
    """A read-only, seekable view of a URL, fetched in cached blocks of BLOCK_BYTES."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url
        self._pos = 0
        self._blocks: OrderedDict[int, bytes] = OrderedDict()
        self.fetched_bytes = 0
        _, content_range = self._fetch(0, 0)
        self.size = int(content_range.rsplit("/", 1)[1])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self.size}[whence]
        self._pos = base + offset
        return self._pos

    def readinto(self, buffer: Buffer) -> int:
        out = memoryview(buffer).cast("B")
        n = max(0, min(len(out), self.size - self._pos))
        done = 0
        while done < n:
            index, offset = divmod(self._pos + done, BLOCK_BYTES)
            chunk = self._block(index)[offset : offset + n - done]
            out[done : done + len(chunk)] = chunk
            done += len(chunk)
        self._pos += n
        return n

    def _block(self, index: int) -> bytes:
        if index in self._blocks:
            self._blocks.move_to_end(index)
            return self._blocks[index]
        start = index * BLOCK_BYTES
        data, _ = self._fetch(start, min(self.size, start + BLOCK_BYTES) - 1)
        self.fetched_bytes += len(data)
        self._blocks[index] = data
        if len(self._blocks) > CACHED_BLOCKS:
            self._blocks.popitem(last=False)
        return data

    def _fetch(self, first: int, last: int) -> tuple[bytes, str]:
        """Bytes first..last inclusive, and the response's Content-Range header."""
        request = urllib.request.Request(self._url, headers={"Range": f"bytes={first}-{last}"})
        for attempt in range(_ATTEMPTS):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return response.read(), response.headers.get("Content-Range", "")
            except (urllib.error.URLError, TimeoutError):
                if attempt == _ATTEMPTS - 1:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")
