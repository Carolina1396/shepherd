"""Check LMDB page bounds BEFORE reading data pages (truncation can SIGBUS).

Run with ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python.
Writes validation.json in the ignored data directory; never edits databases.
"""
import argparse
import json
from pathlib import Path

import lmdb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'omnicorp_lmdb')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    directory = args.data_dir
    report = {}
    for name in ('curies.lmdb', 'shared_counts.lmdb'):
        path = directory / name
        with lmdb.open(str(path), subdir=False, readonly=True, lock=False,
                       readahead=False) as env:
            stats, info = env.stat(), env.info()
            expected = (info['last_pgno'] + 1) * stats['psize']
            actual = path.stat().st_size
            report[name] = {'stat': stats, 'info': info, 'file_bytes': actual,
                            'required_bytes_from_header': expected,
                            'page_bounds_valid': actual >= expected,
                            'missing_bytes': max(0, expected-actual)}
    valid = all(r['page_bounds_valid'] for r in report.values())
    report['safe_to_read_data_pages'] = valid
    (args.report or directory / 'validation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    if not valid:
        raise SystemExit('Database truncated: do not run Omnicorp with these files.')


if __name__ == '__main__':
    main()
