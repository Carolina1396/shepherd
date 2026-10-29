"""Score a converted retrieval graph with frozen pretrained ULTRA 4g."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from retrieve import digest, save

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT.parent / 'ultra/vendor/ULTRA'
CHECKPOINT_HASH = '48a046e708adf5632d87c30eacae01f5f51466b2301effdc2cb42358d22854e0'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a fresh output directory')
    started = time.perf_counter()
    checkpoint = UPSTREAM / 'ckpts/ultra_4g.pth'
    if digest(checkpoint) != CHECKPOINT_HASH:
        raise ValueError('Pretrained 4g checkpoint hash differs from existing ULTRA study')
    dataset = args.dataset
    report = json.loads((dataset/'conversion.json').read_text())
    for name, expected in report['artifacts_sha256'].items():
        if digest(dataset/name) != expected:
            raise ValueError(f'Dataset hash mismatch: {name}')
    cfg = json.loads((dataset/'config.json').read_text())
    candidates = json.loads((dataset/'candidates.json').read_text())
    if not candidates or report['empty_graph']:
        raise ValueError('This scoring runner requires candidates and nonempty evidence')
    os.environ.setdefault('TORCH_EXTENSIONS_DIR', str(ROOT/'results/torch_extensions_cpu'))
    os.environ.setdefault('MAX_JOBS', '2')
    os.environ.setdefault('OMP_NUM_THREADS', '1')
    if args.device == 'cpu':
        # The upstream extension selects CUDA compilation from hardware availability,
        # even for a CPU model. Keep CPU runs independent of the CUDA toolchain.
        os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')
    sys.path.insert(0, str(UPSTREAM))
    import numpy as np
    import torch
    from torch_geometric.data import Data
    from ultra import tasks
    from ultra.models import Ultra

    torch.set_num_threads(1)
    torch.manual_seed(1024)
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable')
    edge_index = torch.from_numpy(np.load(dataset/'edge_index.npy'))
    edge_type = torch.from_numpy(np.load(dataset/'edge_type.npy'))
    graph = tasks.build_relation_graph(Data(edge_index=edge_index, edge_type=edge_type,
        num_nodes=cfg['num_nodes'], num_relations=cfg['num_relations'])).to(args.device)
    common = dict(input_dim=64, hidden_dims=[64]*6, message_func='distmult',
                  aggregate_func='sum', short_cut=True, layer_norm=True)
    model = Ultra(rel_model_cfg={'class': 'RelNBFNet', **common},
                  entity_model_cfg={'class': 'EntityNBFNet', **common})
    model.load_state_dict(torch.load(checkpoint, map_location='cpu')['model'], strict=True)
    model.to(args.device).eval()
    batch = torch.tensor([[c['index'], cfg['anchor']['index'], cfg['target_relation']]
                          for c in candidates], dtype=torch.long, device=args.device).unsqueeze(0)
    if args.device == 'cuda':
        torch.cuda.synchronize()
    tick = time.perf_counter()
    with torch.inference_mode():
        scores = model(graph, batch).squeeze(0).cpu().numpy()
    elapsed = time.perf_counter()-tick
    if scores.shape != (len(candidates),) or not np.isfinite(scores).all():
        raise ValueError('Missing or nonfinite candidate scores')
    # A changed candidate order must not change entity scores.
    with torch.inference_mode():
        reversed_scores = model(graph, batch.flip(1)).squeeze(0).cpu().numpy()[::-1].copy()
    np.testing.assert_allclose(scores, reversed_scores, rtol=1e-5, atol=1e-6)
    ranks = [int(np.count_nonzero(scores >= s)) for s in scores]
    rows = [dict(**c, disease=cfg['anchor']['id'], score=float(s), rank=rank)
            for c, s, rank in zip(candidates, scores, ranks)]
    rows.sort(key=lambda r: (-r['score'], r['id']))
    args.output.mkdir(parents=True)
    np.save(args.output/'scores.npy', scores)
    with (args.output/'ranking.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    # Recompute pessimistic ranks from the written scores, not sorted row positions.
    written = list(csv.DictReader((args.output/'ranking.csv').open()))
    assert {r['id'] for r in written} == {c['id'] for c in candidates}
    assert len(written) == len(candidates)
    for row in written:
        assert int(row['rank']) == sum(float(other['score']) >= float(row['score']) for other in written)
    summary = dict(checkpoint=str(checkpoint.relative_to(ROOT.parent)), checkpoint_sha256=digest(checkpoint),
        ultra_commit=subprocess.check_output(['git','-C',str(UPSTREAM),'rev-parse','HEAD'], text=True).strip(),
        ultra_tracked_code_diff_sha256=__import__('hashlib').sha256(subprocess.check_output(
            ['git','-C',str(UPSTREAM),'diff','HEAD','--','ultra'])).hexdigest(),
        torch_version=torch.__version__, device=args.device, seed=1024, training_updates=0,
        candidates=len(rows), nodes=cfg['num_nodes'], model_edges=int(graph.num_edges),
        relations=cfg['num_relations'], inference_seconds=elapsed,
        total_seconds_including_load_and_verification=time.perf_counter()-started,
        ranking='All returned CURIE candidates, unfiltered, pessimistic ties; ID breaks display ties only',
        verification=dict(finite_scores=True, all_candidates_scored_once=True,
                          candidate_order_invariant=True, saved_ranks_recomputed=True),
        interpretation='Raw model scores, not probabilities. Live graph contains direct treatment evidence. Alias deduplication and benchmark evaluation pending.',
        conversion_sha256=digest(dataset/'conversion.json'), script_sha256=digest(Path(__file__)),
        artifacts_sha256={p.name:digest(p) for p in sorted(args.output.iterdir())}, top_10=rows[:10])
    save(args.output/'summary.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
