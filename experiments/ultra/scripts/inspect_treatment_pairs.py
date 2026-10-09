"""Stream the pinned graph into a small, disk-backed treatment evidence index.

Run from any directory. No third-party Python packages; requires zstd.
Original selected edge records are retained, including qualifiers and provenance.
"""

import argparse
from collections import Counter
from contextlib import contextmanager
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "treatment_pairs"
PREDICATES = {
    "biolink:treats", "biolink:treats_or_applied_or_studied_to_treat",
    "biolink:applied_to_treat", "biolink:studied_to_treat",
    "biolink:in_clinical_trials_for", "biolink:in_preclinical_trials_for",
    "biolink:ameliorates_condition", "biolink:contraindicated_in",
}


@contextmanager
def records(archive, filename):
    """Read one tar member without extracting or loading it into memory."""
    process = subprocess.Popen(
        ["zstd", "-dc", str(archive)], stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as tar:
            for member in tar:
                if member.isfile() and Path(member.name).name == filename:
                    yield tar.extractfile(member)
                    return
        raise FileNotFoundError(f"{filename} missing from {archive}")
    finally:
        # Intentional early stop after the selected member, not an integrity test.
        process.terminate()
        process.stdout.close()
        process.wait()


def labels(value):
    return value if isinstance(value, list) else [value] if value else []


class UnionJSON:
    def __init__(self):
        self.values = set()

    def step(self, value):
        self.values.update(json.loads(value))

    def finalize(self):
        return json.dumps(sorted(self.values))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "download.json").read_text())
    archive_info = next(f for f in manifest["files"] if f["path"].endswith(".tar.zst"))
    archive = ROOT / archive_info["path"]
    if archive.stat().st_size != archive_info["bytes"]:
        raise ValueError("Archive size differs from the download manifest")
    identity = {
        "archive_sha256_from_manifest": archive_info["sha256"],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    summary_path = OUTPUT / "summary.json"
    database = OUTPUT / "evidence.sqlite"
    if not args.refresh and summary_path.exists() and database.exists() and (OUTPUT / "pairs.csv").exists():
        if json.loads(summary_path.read_text()).get("identity") == identity:
            print(f"Using cached analysis: {OUTPUT}", flush=True)
            return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT / "evidence.building.sqlite"
    if temporary.exists():
        raise FileExistsError(f"An unfinished build exists: {temporary}; inspect it before retrying")
    started = time.monotonic()
    counts = Counter()
    with sqlite3.connect(temporary) as db:
        db.execute("PRAGMA temp_store=FILE")
        db.executescript("""
            CREATE TABLE edges (
                row_id INTEGER PRIMARY KEY, edge_id TEXT,
                subject TEXT NOT NULL, object TEXT NOT NULL, predicate TEXT NOT NULL,
                primary_sources TEXT NOT NULL, raw_json TEXT NOT NULL
            );
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY, name TEXT, categories TEXT NOT NULL,
                is_chemical INTEGER, is_disease INTEGER, is_drug INTEGER
            );
        """)
        batch = []
        total = 0
        print("Scanning all edge records (no extraction)...", flush=True)
        with records(archive, "edges.jsonl") as handle:
            for line in handle:
                if not line.strip():
                    continue
                edge = json.loads(line)
                total += 1
                if total % 2_000_000 == 0:
                    print(f"Scanned {total:,} edges; selected {sum(counts.values()):,}", flush=True)
                predicate = edge["predicate"]
                if predicate not in PREDICATES:
                    continue
                sources = sorted({s["resource_id"] for s in edge.get("sources", [])
                                  if s.get("resource_role") == "primary_knowledge_source"
                                  and s.get("resource_id")})
                batch.append((edge.get("id"), edge["subject"], edge["object"], predicate,
                              json.dumps(sources), line.decode().strip()))
                counts[predicate] += 1
                if len(batch) >= 5000:
                    db.executemany("INSERT INTO edges VALUES (NULL,?,?,?,?,?,?)", batch)
                    db.commit()
                    batch.clear()
        db.executemany("INSERT INTO edges VALUES (NULL,?,?,?,?,?,?)", batch)
        db.commit()
        print("Indexing pairs and looking up their node records...", flush=True)
        db.execute("CREATE INDEX edge_pairs ON edges(subject, object)")
        wanted = {row[0] for row in db.execute("SELECT subject FROM edges UNION SELECT object FROM edges")}
        batch = []
        node_count = 0
        with records(archive, "nodes.jsonl") as handle:
            for line in handle:
                if not line.strip():
                    continue
                node = json.loads(line)
                node_count += 1
                if node["id"] not in wanted:
                    continue
                categories = sorted(set(labels(node.get("category"))))
                chemical = bool(set(categories) & {"biolink:ChemicalEntity", "biolink:SmallMolecule", "biolink:Drug"})
                batch.append((node["id"], node.get("name"), json.dumps(categories),
                              int(chemical), int("biolink:Disease" in categories),
                              int("biolink:Drug" in categories)))
                if len(batch) >= 5000:
                    db.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?)", batch)
                    batch.clear()
        db.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?)", batch)
        db.create_aggregate("union_json", 1, UnionJSON)
        db.execute("""CREATE TABLE pairs AS
            SELECT subject, object, COUNT(*) AS edge_count,
                   union_json(json_array(predicate)) AS predicates,
                   union_json(primary_sources) AS primary_sources
            FROM edges GROUP BY subject, object""")
        db.execute("CREATE UNIQUE INDEX pair_ids ON pairs(subject, object)")
        # Exploratory eligibility is explicit; no ontology lookup or approval claim.
        db.execute("""CREATE VIEW candidates AS
            SELECT p.*, s.name AS subject_name, s.categories AS subject_categories,
                   s.is_drug AS subject_is_drug, o.name AS object_name,
                   o.categories AS object_categories
            FROM pairs p JOIN nodes s ON p.subject=s.id JOIN nodes o ON p.object=o.id
            WHERE s.is_chemical=1 AND o.is_disease=1""")
        db.commit()
        scalar = lambda sql: db.execute(sql).fetchone()[0]
        treatment = "biolink:treats"
        contraindication = "biolink:contraindicated_in"
        overlap = []
        for row in db.execute("SELECT predicates, COUNT(*) FROM candidates GROUP BY predicates ORDER BY COUNT(*) DESC"):
            overlap.append({"predicates": json.loads(row[0]), "pairs": row[1]})
        predicate_stats = []
        for predicate, count in counts.most_common():
            unique = db.execute("SELECT COUNT(*) FROM (SELECT subject, object FROM edges WHERE predicate=? GROUP BY subject, object)", (predicate,)).fetchone()[0]
            eligible = db.execute("SELECT COUNT(*) FROM candidates c WHERE EXISTS (SELECT 1 FROM json_each(c.predicates) WHERE value=?)", (predicate,)).fetchone()[0]
            predicate_stats.append({"predicate": predicate, "edges_all_endpoints": count,
                                    "pairs_all_endpoints": unique, "eligible_pairs": eligible})
        summary = {
            "identity": identity, "release": manifest["release"],
            "eligibility": "Subject has ChemicalEntity, SmallMolecule, or Drug; object has Disease in raw category labels. No species or approval filtering.",
            "nodes_scanned": node_count, "edges_scanned": total,
            "selected_edges": sum(counts.values()),
            "unique_pairs_all_endpoints": scalar("SELECT COUNT(*) FROM pairs"),
            "missing_endpoint_ids": len(wanted) - scalar("SELECT COUNT(*) FROM nodes"),
            "eligible_pairs": scalar("SELECT COUNT(*) FROM candidates"),
            "eligible_chemicals": scalar("SELECT COUNT(DISTINCT subject) FROM candidates"),
            "eligible_diseases": scalar("SELECT COUNT(DISTINCT object) FROM candidates"),
            "eligible_pairs_with_multiple_edges": scalar("SELECT COUNT(*) FROM candidates WHERE edge_count>1"),
            "eligible_pairs_with_multiple_primary_sources": scalar("SELECT COUNT(*) FROM candidates WHERE json_array_length(primary_sources)>1"),
            "eligible_chemicals_without_drug_label": scalar("SELECT COUNT(DISTINCT subject) FROM candidates WHERE subject_is_drug=0"),
            "eligible_pairs_without_drug_label": scalar("SELECT COUNT(*) FROM candidates WHERE subject_is_drug=0"),
            "treats_and_contraindicated_pairs": sum(row["pairs"] for row in overlap if {treatment, contraindication}.issubset(row["predicates"])),
            "predicate_stats": predicate_stats, "predicate_combinations": overlap,
        }
        metadata_info = next(f for f in manifest["files"] if f["path"].endswith("graph-metadata.json"))
        metadata = json.loads((ROOT / metadata_info["path"]).read_text())
        summary["matches_metadata_totals"] = (
            node_count == metadata["schema"]["nodes_summary"]["total_count"]
            and total == metadata["schema"]["edges_summary"]["total_count"]
        )
        cursor = db.execute("""SELECT subject AS chemical_id, subject_name AS chemical_name,
            subject_categories AS chemical_categories, object AS disease_id,
            object_name AS disease_name, object_categories AS disease_categories,
            predicates, primary_sources, edge_count, subject_is_drug
            FROM candidates ORDER BY subject, object""")
        csv_temp = OUTPUT / "pairs.building.csv"
        with csv_temp.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([column[0] for column in cursor.description])
            writer.writerows(cursor)
    temporary.replace(database)
    csv_temp.replace(OUTPUT / "pairs.csv")
    summary["elapsed_seconds"] = round(time.monotonic() - started, 1)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Complete: {summary['eligible_pairs']:,} eligible pairs. Outputs: {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
