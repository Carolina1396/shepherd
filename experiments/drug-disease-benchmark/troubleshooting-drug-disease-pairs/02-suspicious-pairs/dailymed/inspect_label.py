"""Extract section-aware evidence from the downloaded DailyMed SPL XML."""
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
NS = {"s": "urn:hl7-org:v3"}


def text(element):
    return " ".join(" ".join(element.itertext()).split()) if element is not None else ""


def main():
    path = HERE.parents[1] / "04-parser-investigation/fixtures/naproxen.xml"
    root = ET.parse(path).getroot()
    sections = []
    for section in root.findall(".//s:section", NS):
        code = section.find("s:code", NS)
        body = text(section.find("s:text", NS))
        sections.append({
            "code": code.attrib if code is not None else {},
            "title": text(section.find("s:title", NS)),
            "text": body,
            "contains_heart_failure": "heart failure" in body.lower(),
            "contains_toothache": "toothache" in body.lower(),
        })
    result = {
        "source_file": os.path.relpath(path, HERE),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "set_id": root.find("s:setId", NS).get("root"),
        "document_id": root.find("s:id", NS).get("root"),
        "version": root.find("s:versionNumber", NS).get("value"),
        "effective_time": root.find("s:effectiveTime", NS).get("value"),
        "application_numbers": sorted({e.get("extension") for e in root.findall(".//s:approval/s:id", NS) if e.get("extension")}),
        "sections": sections,
    }
    output = HERE / "label-sections.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "sections"}, indent=2))
    for section in sections:
        if section["contains_heart_failure"] or section["contains_toothache"]:
            print(section["title"], section["code"].get("code"),
                  "heart_failure=", section["contains_heart_failure"],
                  "toothache=", section["contains_toothache"])


if __name__ == "__main__":
    main()
