import csv
import re
import os

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
os.makedirs(os.path.join(PROJECT_DIR, "output"), exist_ok=True)
input_path  = os.path.join(PROJECT_DIR, "output", "api_mapping_output.md")
output_path = os.path.join(PROJECT_DIR, "output", "mdm_mapping_output.csv")

HEADERS = ["ID", "MDM Attribute Name", "MDM Field Group", "MDM API Name",
           "MDM Data Type", "Source Table", "Source Field", "Mapping Status", "Notes"]

rows = []

with open(input_path, "r") as f:
    for line in f:
        line = line.rstrip()
        if not line.startswith("|"):
            continue
        # Skip separator rows
        if re.match(r"^\|[-| :]+\|$", line):
            continue

        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c != ""]

        # Only keep rows where the first cell is an attribute ID like A001 or B001
        if not cells or not re.match(r'^[AB]\d+$', cells[0]):
            continue

        while len(cells) < len(HEADERS):
            cells.append("")
        cells = cells[:len(HEADERS)]
        rows.append(cells)

with open(output_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(HEADERS)
    writer.writerows(rows)

print(f"Done. {len(rows)} rows written to: {output_path}")
