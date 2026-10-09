"""Read Gandalf categories to reconstruct the bidirectional study candidates."""
import argparse
import json
from pathlib import Path

from gandalf.node_store import NodeStore

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Refusing to overwrite {args.output}")
    prepared = ROOT / "output/full-graph-ultra/run_001/data"
    labels = json.loads((prepared / "labels.json").read_text())
    original = json.loads((prepared / "candidates.json").read_text())
    drugs, diseases = [], []
    with NodeStore(ROOT / "output/gandalf/full-store/node_store.lmdb", readonly=True) as store:
        for idx, props in store.iter_properties():
            categories = props.get("categories", [])
            if "biolink:Drug" in categories:
                drugs.append(idx)
            if "biolink:Disease" in categories:
                diseases.append(idx)
        assert set(drugs) == {r["index"] for r in original}
        assert len(drugs) == 5326 and len(diseases) == 51707
        ids = store.get_node_ids_batch(drugs + diseases)
        for row in original:
            assert ids[row["index"]] == row["id"]
        for row in labels:
            assert ids[row["drug_index"]] == row["drug"]
            assert ids[row["disease_index"]] == row["disease"]
    result = {name: [{"index": i, "id": ids[i]} for i in sorted(indices)]
              for name, indices in (("disease_to_drug", drugs), ("drug_to_disease", diseases))}
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    temporary.replace(args.output)
    print("Verified 5,326 Drug and 51,707 Disease candidates against Gandalf", flush=True)


if __name__ == "__main__":
    main()
