import os, csv, re, json
from flask import Flask, render_template, request, send_file, jsonify, Response, stream_with_context
from datetime import date
import anthropic

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

# Load .env
env_path = os.path.join(SCRIPT_DIR, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

app = Flask(__name__)

INPUT_FILE  = os.path.join(PROJECT_DIR, "input file", "datasystem.txt")
OUTPUT_DIR  = os.path.join(PROJECT_DIR, "output")
MD_PATH     = os.path.join(OUTPUT_DIR, "api_mapping_output.md")
CSV_PATH    = os.path.join(OUTPUT_DIR, "mdm_mapping_output.csv")
DRAWIO_PATH = os.path.join(OUTPUT_DIR, "mdm_mapping.drawio")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = ["ID", "MDM Attribute Name", "MDM Field Group", "MDM API Name",
           "MDM Data Type", "Source Table", "Source Field", "Source Data Type", "Mapping Status", "Notes"]

# ── Pipeline steps ────────────────────────────────────────────────────────────

def step_api_mapping(text: str):
    with open(os.path.join(SCRIPT_DIR, "mapping_prompt.md")) as f:
        system_prompt = f.read()
    with open(os.path.join(SCRIPT_DIR, "ootb_reference.txt")) as f:
        ootb_file = f.read()

    user_message = (
        f"<SOURCE_SYSTEM_FILE>\n{text}\n</SOURCE_SYSTEM_FILE>\n\n"
        f"<OOTB_REFERENCE_FILE>\n{ootb_file}\n</OOTB_REFERENCE_FILE>\n\n"
        "Produce the full MDM mapping document following all instructions in the system prompt."
    )

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    full_text = ""
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    ) as stream:
        for chunk in stream.text_stream:
            full_text += chunk
            yield ("token", chunk)
        final = stream.get_final_message()

    with open(MD_PATH, "w") as f:
        f.write(full_text)
    yield ("done", (final.usage.input_tokens, final.usage.output_tokens))


def step_convert_csv():
    rows = []
    with open(MD_PATH) as f:
        for line in f:
            line = line.rstrip()
            if not line.startswith("|"):
                continue
            if re.match(r"^\|[-| :]+\|$", line):
                continue
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c != ""]
            if not cells or not re.match(r'^[AB]\d+$', cells[0]):
                continue
            while len(cells) < len(HEADERS):
                cells.append("")
            rows.append(cells[:len(HEADERS)])

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        writer.writerows(rows)
    return rows


def step_generate_diagram():
    from output_generators import save_drawio_file

    CUSTOM_STATUSES = {"Custom"}
    SKIP_STATUSES   = {"Not Required"}
    ROOT_GROUPS     = {"ROOT", "CUSTOM", ""}

    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    fields, seen = [], set()
    for row in rows:
        status      = row.get("Mapping Status", "").strip()
        api_name    = row.get("MDM API Name", "").strip()
        mdm_name    = row.get("MDM Attribute Name", "").strip()
        field_group = row.get("MDM Field Group", "").strip()
        data_type   = row.get("MDM Data Type", "").strip()
        notes       = row.get("Notes", "").strip()
        attr_id     = row.get("ID", "").strip()

        if status in SKIP_STATUSES:
            continue
        if api_name in ("—", "-", "--"):
            if status == "Custom":
                words = mdm_name.replace("/", " ").replace("(", "").replace(")", "").split()
                slug = "_".join(w.lower() for w in words)
                api_name = slug if slug.startswith("x_") else f"x_{slug}"
            else:
                continue
        if not api_name or not attr_id:
            continue

        label = mdm_name if mdm_name else api_name
        key = f"{field_group}:{api_name}:{label}"
        if key in seen:
            continue
        seen.add(key)

        is_custom  = status in CUSTOM_STATUSES
        is_lookup  = "Lookup" in data_type or "lookup" in data_type.lower()
        lookup_entity = ""
        if is_lookup and "→" in data_type:
            lookup_entity = data_type.split("→")[-1].strip()

        if field_group in ROOT_GROUPS or field_group == "ROOT (system)":
            fg = "ROOT"
        elif field_group == "CUSTOM":
            fg = "CUSTOM"
        else:
            fg = field_group

        fields.append({
            "name": api_name, "displayName": label, "dataType": data_type,
            "fieldGroup": fg, "isCustom": is_custom, "isLookup": is_lookup,
            "lookupEntity": lookup_entity,
            "description": notes[:120] + "..." if len(notes) > 120 else notes,
            "mappingStatus": status,
        })

    data_model = {
        "metadata": {"generatedDate": str(date.today()), "platform": "informatica"},
        "reasoning": {
            "summary": "MDM Person Entity mapping generated from source system.",
            "entityDecisions": [], "fieldDecisions": []
        },
        "dataModel": {
            "entities": [{
                "name": "Person", "type": "BusinessEntity",
                "description": "MDM Person Entity — UNSW SIMS to Informatica MDM mapping",
                "fields": fields
            }],
            "relationships": []
        }
    }

    save_drawio_file(data_model, DRAWIO_PATH)
    return len(fields)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    file = request.files.get("file")
    text = request.form.get("text", "").strip()

    if file and file.filename:
        text = file.read().decode("utf-8")
    if not text:
        return jsonify({"error": "No input provided"}), 400

    os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
    with open(INPUT_FILE, "w") as f:
        f.write(text)

    def stream():
        try:
            # Flush Werkzeug's response buffer so the browser starts reading immediately
            yield ": " + " " * 4096 + "\n\n"
            yield f"data: {json.dumps({'step': 1, 'status': 'running', 'message': 'Calling Claude AI…'})}\n\n"
            in_tok = out_tok = 0
            for event, payload in step_api_mapping(text):
                if event == "token":
                    yield f"data: {json.dumps({'step': 1, 'status': 'token', 'chunk': payload})}\n\n"
                else:
                    in_tok, out_tok = payload
            yield f"data: {json.dumps({'step': 1, 'status': 'done', 'message': f'AI response received ({in_tok} input / {out_tok} output tokens)'})}\n\n"

            yield f"data: {json.dumps({'step': 2, 'status': 'running', 'message': 'Parsing markdown table → CSV…'})}\n\n"
            rows = step_convert_csv()
            yield f"data: {json.dumps({'step': 2, 'status': 'done', 'message': f'{len(rows)} mapping rows extracted'})}\n\n"

            yield f"data: {json.dumps({'step': 3, 'status': 'running', 'message': 'Generating Draw.io diagram…'})}\n\n"
            field_count = step_generate_diagram()
            yield f"data: {json.dumps({'step': 3, 'status': 'done', 'message': f'{field_count} fields mapped to diagram nodes'})}\n\n"

            yield f"data: {json.dumps({'step': 'complete', 'csv': [HEADERS] + rows})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'step': 'error', 'message': str(e)})}\n\n"

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    )


@app.route("/generate-diagram", methods=["POST"])
def generate_diagram_direct():
    from output_generators import save_drawio_file

    raw = request.form.get("input", "").strip()
    if not raw:
        return jsonify({"error": "No input provided"}), 400

    CUSTOM_STATUSES = {"Custom"}
    SKIP_STATUSES   = {"Not Required"}
    ROOT_GROUPS     = {"ROOT", "CUSTOM", ""}

    fields, seen = [], set()
    current_group = "ROOT"
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # [GROUP_NAME] header
        if line.startswith("[") and line.endswith("]"):
            current_group = line[1:-1].strip()
            continue
        # Field line: apiName | Display Name | Type  (optional: | derived / custom / skip)
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        api_name    = parts[0]
        mdm_name    = parts[1]
        data_type   = parts[2] if len(parts) > 2 else "Text"
        flag        = parts[3].lower() if len(parts) > 3 else ""
        field_group = current_group

        if flag in ("skip", "not required"):
            status = "Not Required"
        elif flag in ("derived", "ootb (derived)", "ootb(derived)"):
            status = "OOTB (Derived)"
        elif flag in ("custom",):
            status = "Custom"
        else:
            status = "OOTB"

        if status in SKIP_STATUSES or not api_name:
            continue

        key = f"{field_group}:{api_name}:{mdm_name}"
        if key in seen:
            continue
        seen.add(key)

        is_custom  = status in CUSTOM_STATUSES
        is_lookup  = "lookup" in data_type.lower() or "→" in data_type
        lookup_entity = data_type.split("→")[-1].strip() if is_lookup and "→" in data_type else ""

        if field_group in ROOT_GROUPS or field_group.upper() in ("ROOT", "ROOT (SYSTEM)"):
            fg = "ROOT"
        elif field_group.upper() == "CUSTOM":
            fg = "CUSTOM"
        else:
            fg = field_group

        fields.append({
            "name": api_name, "displayName": mdm_name, "dataType": data_type,
            "fieldGroup": fg, "isCustom": is_custom, "isLookup": is_lookup,
            "lookupEntity": lookup_entity, "description": "",
            "mappingStatus": status,
        })

    if not fields:
        return jsonify({"error": "No valid rows found. Check your input format."}), 400

    out_path = os.path.join(PROJECT_DIR, "output", "diagram_builder_output.drawio")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    data_model = {
        "metadata": {"generatedDate": str(date.today()), "platform": "informatica"},
        "reasoning": {"summary": "Diagram Builder output.", "entityDecisions": [], "fieldDecisions": []},
        "dataModel": {
            "entities": [{"name": "Person", "type": "BusinessEntity",
                          "description": "Generated from Diagram Builder", "fields": fields}],
            "relationships": []
        }
    }
    save_drawio_file(data_model, out_path)
    with open(out_path) as f:
        xml = f.read()
    return jsonify({"xml": xml, "fields": len(fields)})


@app.route("/process-diagram-input", methods=["POST"])
def process_diagram_input():
    raw = request.form.get("raw", "").strip()
    if not raw:
        return jsonify({"error": "No input provided"}), 400

    system_prompt = (
        "You are an MDM field mapping assistant. The user will give you a list of fields "
        "in any format — free text, CSV, table, numbered list, or Draw.io XML (.drawio file). "
        "If given Draw.io XML, extract the field labels from the diagram cell values.\n"
        "Convert them into the structured format below. Output ONLY the structured text — "
        "no explanation, no markdown code fences, no extra commentary.\n\n"
        "Output format:\n"
        "[GROUP_NAME]\n"
        "apiName | Display Name | DataType | flag\n\n"
        "Grouping rules:\n"
        "- ROOT: core person fields (name, dob, gender, deceased, nationality, title, suffix)\n"
        "- ADDRESS: any address or location fields\n"
        "- EMAIL: email address fields\n"
        "- PHONE: phone/mobile/fax fields\n"
        "- IDENTIFIER: IDs, passport, tax file, employee number, student ID, government IDs\n"
        "- ALTERNATE NAMES: preferred name, display name, other name variants\n"
        "- CUSTOM: anything that doesn't fit the above\n\n"
        "Field rules:\n"
        "- apiName: camelCase (e.g. firstName, dateOfBirth, taxFileNumber)\n"
        "- Display Name: human-readable label\n"
        "- DataType: Text / Integer / Date / DateTime / Boolean / Lookup\n"
        "  Use Lookup for coded reference fields (gender, country, type codes, etc.)\n"
        "  Use Boolean for yes/no or flag fields\n"
        "- flag (optional, omit if standard OOTB): 'derived' if computed, 'custom' if non-standard\n"
        "- Separate groups with one blank line\n"
        "- Every field from the input must appear in the output"
    )

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Convert these fields:\n\n{raw}"}]
    )
    return jsonify({"structured": response.content[0].text.strip()})


@app.route("/api/drawio-xml")
def drawio_xml():
    if not os.path.exists(DRAWIO_PATH):
        return "Not generated yet", 404
    with open(DRAWIO_PATH, "r") as f:
        return f.read(), 200, {"Content-Type": "text/xml"}


@app.route("/download/<name>")
def download(name):
    DIAGRAM_BUILDER_PATH = os.path.join(PROJECT_DIR, "output", "diagram_builder_output.drawio")
    paths = {"csv": CSV_PATH, "drawio": DRAWIO_PATH, "md": MD_PATH, "diagram": DIAGRAM_BUILDER_PATH}
    if name not in paths or not os.path.exists(paths[name]):
        return "File not found", 404
    return send_file(paths[name], as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=5001, threaded=True)
