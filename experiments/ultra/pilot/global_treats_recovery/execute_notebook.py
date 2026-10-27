"""Execute notebook 05 in IPython and save actual rich outputs."""
import json
from pathlib import Path
import queue
import time

from jupyter_client import KernelManager

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / 'notebooks/05_global_treats_recovery.ipynb'
notebook = json.loads(path.read_text())
manager = KernelManager(kernel_name='python3')
manager.start_kernel(cwd=str(ROOT))
client = manager.client()
client.start_channels()
try:
    client.wait_for_ready(timeout=60)
    for number, cell in enumerate(notebook['cells']):
        if cell['cell_type'] != 'code':
            continue
        cell['outputs'] = []
        message_id = client.execute(cell['source'], stop_on_error=True)
        deadline = time.monotonic() + 7200
        error = None
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError(f'Notebook cell {number}')
            try:
                msg = client.get_iopub_msg(timeout=1)
            except queue.Empty:
                continue
            if msg.get('parent_header', {}).get('msg_id') != message_id:
                continue
            kind, content = msg['header']['msg_type'], msg['content']
            if kind == 'execute_input':
                cell['execution_count'] = content['execution_count']
            elif kind == 'stream':
                cell['outputs'].append({'output_type': kind, 'name': content['name'], 'text': content['text']})
            elif kind in ('display_data', 'execute_result'):
                output = {'output_type': kind, 'data': content['data'], 'metadata': content.get('metadata', {})}
                if kind == 'execute_result':
                    output['execution_count'] = content['execution_count']
                cell['outputs'].append(output)
            elif kind == 'error':
                error = content
                cell['outputs'].append({'output_type': 'error', **{k: content[k] for k in ('ename', 'evalue', 'traceback')}})
            elif kind == 'status' and content['execution_state'] == 'idle':
                break
        path.write_text(json.dumps(notebook, indent=1) + '\n')
        print(f'Executed cell {number}', flush=True)
        if error:
            raise RuntimeError('\n'.join(error['traceback']))
    assert all(c['execution_count'] is not None for c in notebook['cells'] if c['cell_type'] == 'code')
    print('Saved executed notebook:', path)
finally:
    client.stop_channels()
    manager.shutdown_kernel(now=True)
    del client
