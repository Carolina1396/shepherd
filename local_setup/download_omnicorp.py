"""Download the published single-file Omnicorp LMDBs (not tar archives).

Historical diagnostic only: the published shared_counts.lmdb was truncated.
For a working installation use the archive procedure in local_setup/README.txt.
Do not run this against the working archive-derived dataset.
Existing completed files are never overwritten. Partial files can be retried.
Records source headers and local SHA-256 checksums in the ignored data folder.
"""
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

BASE = 'https://stars.renci.org/var/translator/shepherd/'
OUT = Path(__file__).resolve().parents[1] / 'omnicorp_lmdb'


def main():
    OUT.mkdir(exist_ok=True)
    records = []
    for name in ('curies.lmdb', 'shared_counts.lmdb'):
        url = BASE + name
        with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=60) as response:
            size = int(response.headers['Content-Length'])
            record = {'file': name, 'url': url, 'bytes': size,
                      'etag': response.headers.get('ETag'),
                      'last_modified': response.headers.get('Last-Modified')}
        path = OUT / name
        if not path.exists():
            if shutil.disk_usage(OUT).free < size + 1024**3:
                raise RuntimeError('Insufficient disk space')
            partial = path.with_suffix('.lmdb.part')
            print(f'Downloading {name}: {size:,} bytes', flush=True)
            with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as stream:
                if response.headers.get('ETag') != record['etag']:
                    raise RuntimeError('Source changed between HEAD and GET')
                shutil.copyfileobj(response, stream, length=1024**2)
            if partial.stat().st_size != size:
                raise RuntimeError(f'Incomplete download: {name}')
            partial.rename(path)
        if path.stat().st_size != size:
            raise RuntimeError(f'Existing {name} has a different size; refusing to overwrite')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024**2), b''):
                digest.update(chunk)
        record['sha256'] = digest.hexdigest()
        records.append(record)
        print(json.dumps(record), flush=True)
    (OUT / 'download_manifest.json').write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    main()
