import hashlib
import os
import pathlib
import shutil
import tempfile
import typing
from urllib.request import Request, urlopen


def download_url_to_file(
    url: str, dst: pathlib.Path, hash: str = None, callback: typing.Callable[[float], None] = None
):
    file_size = None
    total_downloaded = 0
    if hash is not None:
        calc_hash = hashlib.sha256()
    req = Request(url)
    response = urlopen(req)
    meta = response.info()
    if hasattr(meta, "getheaders"):
        content_length = meta.getheaders("Content-Length")
    else:
        content_length = meta.get_all("Content-Length")

    if content_length is not None and len(content_length) > 0:
        file_size = int(content_length[0])
    dst.parent.mkdir(parents=True, exist_ok=True)
    f = tempfile.NamedTemporaryFile(delete=False, dir=dst.parent)
    try:
        while True:
            buffer = response.read(8192)
            if len(buffer) == 0:
                break
            total_downloaded += len(buffer)
            f.write(buffer)
            if hash:
                calc_hash.update(buffer)
            if callback is not None:
                callback(100 * total_downloaded / file_size)
        f.close()
        if hash is not None:
            digest = calc_hash.hexdigest()
            if digest != hash:
                raise RuntimeError(f'Invalid hash value (expected "{hash}", got "{digest}")')
        shutil.move(f.name, dst)
    finally:
        f.close()
        if os.path.exists(f.name):
            os.remove(f.name)
