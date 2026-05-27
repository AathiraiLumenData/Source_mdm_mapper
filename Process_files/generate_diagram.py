"""
generate_diagram.py
Reads mdm_mapping_output.csv and generates a Draw.io diagram.
"""

import csv
import os
from datetime import date
from output_generators import save_drawio_file

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
os.makedirs(os.path.join(PROJECT_DIR, "output"), exist_ok=True)
CSV_PATH = os.path.join(PROJECT_DIR, "output", "mdm_mapping_output.csv")
OUT_PATH = os.path.join(PROJECT_DIR, "output", "mdm_mapping.drawio")

# Mapping Status values that mean the field is custom
CUSTOM_STATUSES = {"Custom"}

# Mapping Status values to skip (no real MDM field to draw)
SKIP_STATUSES = {"Not Required"}

# MDM groups that are standalone (no sub-group expansion needed)
ROOT_GROUPS = {"ROOT", "CUSTOM", ""}


def parse_csv(path: str) -> list:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def build_data_model(rows: list) -> dict:
    fields = []
    seen = set()  # avoid duplicate API names per group

    for row in rows:
        status = row.get("Mapping Status", "").strip()
        api_name = row.get("MDM API Name", "").strip()
        mdm_name = row.get("MDM Attribute Name", "").strip()
        field_group = row.get("MDM Field Group", "").strip()
        data_type = row.get("MDM Data Type", "").strip()
        notes = row.get("Notes", "").strip()
        attr_id = row.get("ID", "").strip()

        # Skip platform-managed fields (no source, no MDM field to draw)
        if status in SKIP_STATUSES:
            continue

        # For custom fields with no API name, generate X_ prefixed name
        if api_name in ("—", "-", "--"):
            if status == "Custom":
                # Convert MDM Attribute Name to camelCase with X_ prefix
                words = mdm_name.replace("/", " ").replace("(", "").replace(")", "").split()
                camel = words[0].lower() + "".join(w.capitalize() for w in words[1:])
                api_name = camel if camel.lower().startswith("x_") else f"X_{camel}"
            else:
                continue

        # Skip rows with no API name or attribute ID
        if not api_name or not attr_id:
            continue

        # Use display name as the node label
        label = mdm_name if mdm_name else api_name

        # Dedup: same api_name + field_group combo
        key = f"{field_group}:{api_name}:{label}"
        if key in seen:
            continue
        seen.add(key)

        is_custom = status in CUSTOM_STATUSES
        is_lookup = "Lookup" in data_type or "lookup" in data_type.lower()
        # Extract lookup entity name from data type string e.g. "Lookup → Country"
        lookup_entity = ""
        if is_lookup and "→" in data_type:
            lookup_entity = data_type.split("→")[-1].strip()

        # Determine fieldGroup for the generator
        # ROOT and CUSTOM fields are standalone; everything else gets grouped
        if field_group in ROOT_GROUPS or field_group == "ROOT (system)":
            fg = "ROOT"
        elif field_group == "CUSTOM":
            fg = "CUSTOM"
        else:
            fg = field_group  # e.g. ADDRESS, EMAIL, PHONE, IDENTIFIER, etc.

        fields.append({
            "name": api_name,
            "displayName": label,
            "dataType": data_type,
            "fieldGroup": fg,
            "isCustom": is_custom,
            "isLookup": is_lookup,
            "lookupEntity": lookup_entity,
            "description": notes[:120] + "..." if len(notes) > 120 else notes,
            "mappingStatus": status,
        })

    data_model = {
        "metadata": {
            "generatedDate": str(date.today()),
            "platform": "informatica"
        },
        "reasoning": {
            "summary": "MDM Person Entity mapping generated from SIMS (PeopleSoft) source system attributes.",
            "entityDecisions": [],
            "fieldDecisions": []
        },
        "dataModel": {
            "entities": [
                {
                    "name": "Person",
                    "type": "BusinessEntity",
                    "description": "MDM Person Entity — UNSW SIMS to Informatica MDM mapping",
                    "fields": fields
                }
            ],
            "relationships": []
        }
    }

    return data_model


def main():
    print(f"Reading: {CSV_PATH}")
    rows = parse_csv(CSV_PATH)
    print(f"  {len(rows)} rows found in CSV")

    data_model = build_data_model(rows)
    field_count = len(data_model["dataModel"]["entities"][0]["fields"])
    print(f"  {field_count} fields mapped to diagram nodes")

    save_drawio_file(data_model, OUT_PATH)


if __name__ == "__main__":
    main()
