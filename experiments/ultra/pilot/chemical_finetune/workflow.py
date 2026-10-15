"""Train, select by validation MRR, evaluate test, and independently verify results."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_graph_common import digest, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    status_file = output.with_suffix('.status.json')
    record = {'started_unix': time.time(), 'complete': False, 'phase': 'training'}
    save(status_file, record)
    code = 1
    read = lambda path: json.loads(path.read_text())
    runner = ['bash', str(ROOT / 'scripts/gpu_python.sh'), '-B', '-u',
              str(Path(__file__).with_name('run.py')), '--output', str(output)]
    try:
        code = subprocess.run(runner + (['--resume'] if args.resume else []), cwd=REPO).returncode
        if code == 0:
            record['phase'] = 'test'
            save(status_file, record)
            code = subprocess.run(runner + ['--test-only'], cwd=REPO).returncode
        if code == 0:
            record['phase'] = 'verification'
            save(status_file, record)
            code = subprocess.run([str(ROOT / '.venv/bin/python'), '-B', '-u',
                                   str(Path(__file__).with_name('verify_results.py')),
                                   '--output', str(output)], cwd=REPO).returncode
        if code == 0:
            done = read(output / 'completed.json')
            settings = read(output / 'settings.json')
            prepared = Path(settings['prepared_dataset'])
            verification = read(output / 'verification.json')
            assert verification['complete']
            validation_dir = (prepared / 'evaluation/validation' if done['best_step'] == 0
                              else output / f"validation_step_{done['best_step']:06d}")
            compact = lambda value: {k: v for k, v in value.items() if k != 'score_files_sha256'}
            result = {
                'experiment': 11, 'complete': True, 'run_directory': str(output),
                'training': done, 'settings': settings, 'score_verification': verification,
                'results': {'validation': compact(read(validation_dir / 'metrics.json')),
                            'test': compact(read(output / 'test/metrics.json'))},
                'pretrained_experiment10': {
                    s: compact(read(prepared / f'evaluation/{s}/metrics.json'))
                    for s in ['validation', 'test']},
                'training_peak_gpu_allocated_bytes': max(
                    read(path)['peak_gpu_allocated_bytes'] for path in (output / 'steps').glob('*.json')),
                'test_resources': read(output / 'test/resources.json'),
                'workflow_sha256': digest(Path(__file__)),
            }
            save(output / 'results.json', result)
            save(ROOT / 'pilot/studies' / f'{output.name}_results.json', result)
            record.update(complete=True, phase='complete')
    except Exception as error:
        code = 1
        record['error'] = repr(error)
        traceback.print_exc()
    finally:
        record.update(exit_code=code, finished_unix=time.time())
        if code:
            record.update(complete=False, phase='failed')
        save(status_file, record)
    raise SystemExit(code)


if __name__ == '__main__':
    main()
