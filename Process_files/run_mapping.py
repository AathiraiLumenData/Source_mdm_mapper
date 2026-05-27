import anthropic
import os

# --- Load .env file ---
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
env_path = os.path.join(SCRIPT_DIR, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# --- Config ---
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL   = "claude-sonnet-4-6"
DIR     = SCRIPT_DIR

# --- Load files ---
with open(os.path.join(DIR, "mapping_prompt.md"),  "r") as f:
    system_prompt = f.read()

with open(os.path.join(PROJECT_DIR, "input file", "datasystem.txt"), "r") as f:
    source_file = f.read()

with open(os.path.join(DIR, "ootb_reference.txt"), "r") as f:
    ootb_file = f.read()

# --- Build user message ---
user_message = f"""<SOURCE_SYSTEM_FILE>
{source_file}
</SOURCE_SYSTEM_FILE>

<OOTB_REFERENCE_FILE>
{ootb_file}
</OOTB_REFERENCE_FILE>

Produce the full MDM mapping document following all instructions in the system prompt."""

# --- API call ---
client = anthropic.Anthropic(api_key=API_KEY)

print("Calling Anthropic API... this may take 30-60 seconds.\n")

response = client.messages.create(
    model=MODEL,
    max_tokens=16000,
    system=system_prompt,
    messages=[{"role": "user", "content": user_message}]
)

output = response.content[0].text

# --- Save output ---
os.makedirs(os.path.join(PROJECT_DIR, "output"), exist_ok=True)
out_path = os.path.join(PROJECT_DIR, "output", "api_mapping_output.md")
with open(out_path, "w") as f:
    f.write(output)

print(f"Done. Output saved to: {out_path}")
print(f"\nTokens used — input: {response.usage.input_tokens}, output: {response.usage.output_tokens}")
