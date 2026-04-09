"""
Debug test script — runs automation with extra logging at each phase.
"""
import os
import json
from dotenv import load_dotenv
from agent import WebAgent
from excel_config import (
    load_hierarchy_configs_from_master_data,
    load_menu_target_from_sheet,
    load_runtime_config_from_excel,
)

load_dotenv(override=True)

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
MODEL = os.environ.get("MODEL", "gpt-4o-mini")
APP_URL = os.environ.get("APP_URL", "http://dev1803.dev.e2open.com:9880/Main.action")
EXCEL_PATH = os.environ.get("EXCEL_PATH", "input.xlsx")
EXCEL_CREDENTIALS_SHEET = os.environ.get("EXCEL_CREDENTIALS_SHEET", "Credentials")
EXCEL_MENU_SHEET = os.environ.get("EXCEL_MENU_SHEET", "Master data")
KEEP_OPEN = os.environ.get("KEEP_OPEN", "true").strip().lower() in {"1", "true", "yes", "y"}

# Load Excel data
print("[DEBUG] Loading Excel data...", flush=True)
runtime = load_runtime_config_from_excel(
    file_path=EXCEL_PATH,
    sheet_name=EXCEL_CREDENTIALS_SHEET or None,
    row_index=1,
)
print(f"[DEBUG] Loaded runtime: username={runtime.app_username}, customer={runtime.customer_name}, config={runtime.configuration_number}", flush=True)

# Load menu target
if EXCEL_MENU_SHEET.strip():
    runtime.menu_group = EXCEL_MENU_SHEET
    runtime.menu_item = load_menu_target_from_sheet(EXCEL_PATH, EXCEL_MENU_SHEET)
    print(f"[DEBUG] Menu target: {runtime.menu_group} -> {runtime.menu_item}", flush=True)

# Load hierarchy configs
print("[DEBUG] Loading hierarchy configs from Master data...", flush=True)
master_data_hierarchy_configs = load_hierarchy_configs_from_master_data(EXCEL_PATH, EXCEL_MENU_SHEET)
print(f"[DEBUG] Loaded {len(master_data_hierarchy_configs)} hierarchy configs", flush=True)
for i, cfg in enumerate(master_data_hierarchy_configs):
    print(f"[DEBUG]   [{i}] {cfg.hierarchy_key}: {cfg.hierarchy_name} -> {cfg.levels}", flush=True)

# Build task with explicit phase markers
TASK = f"""
PHASE 1: LOGIN
Navigate to {APP_URL} and log in with:
    - Username: {runtime.app_username}
    - Password: {runtime.app_password}

Steps:
1. Go to the URL.
2. Find the username and password fields and fill them in.
3. Submit the login form.
4. Confirm you are logged in (page title changes or customer dropdown appears).
5. Wait 2 seconds and report login success with current URL.

PHASE 2: CUSTOMER SELECTION
6. The page content lives inside an iframe (use get_frames to identify it).
7. In that frame, find and select the Customer Name dropdown:
   - Use get_select_options_in_frame to list all options.
   - Select exact customer name (case-insensitive exact label) only: "{runtime.customer_name}".
   - Do not choose any other customer. If not available, return an error.
8. After selecting the customer, open configuration number "{runtime.configuration_number}"
   in read-only mode using open_configuration_read_only_in_frame.
9. Confirm the read-only view opened. Report success with current URL.

PHASE 3: MENU NAVIGATION
10. Open left menu using open_left_menu_item with:
    - menu_group="{runtime.menu_group}"
    - menu_item="{runtime.menu_item}"
11. Confirm the {runtime.menu_item} screen opened. Report success with current URL and title.

PHASE 4: HIERARCHY CONFIGURATION (First Hierarchy Only)
12. On Hierarchy screen, click "Add New" to open Add Hierarchy Configuration dialog.
13. Set "Hierarchy Name" field to "{master_data_hierarchy_configs[0].hierarchy_name}".
14. Under "Hierarchy Levels" section, add each level sequentially in the given order:
    - Type level name in the Name field: {json.dumps(master_data_hierarchy_configs[0].levels)}
    - Click Add after each level.
    - Repeat for every level.
15. Click Save.
16. Report all phases completed with final status.

Rules:
- Do NOT invent values.
- Use exact values and exact order.
- If a field/button is missing, report the phase where it failed.
"""

print("[DEBUG] Task prompt built. Starting agent...", flush=True)
print("[DEBUG] KEEP_OPEN =", KEEP_OPEN, flush=True)

if __name__ == "__main__":
    agent = WebAgent(
        github_token=GITHUB_TOKEN,
        model=MODEL,
        headless=False,
        keep_open=KEEP_OPEN,
    )
    print("[DEBUG] Agent created. Running task...", flush=True)
    try:
        summary = agent.run(TASK)
        print("\n[DEBUG] ===== AGENT COMPLETED =====")
        print(summary)
    except Exception as e:
        print(f"\n[DEBUG] ===== AGENT ERROR =====")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {e}")
        import traceback
        traceback.print_exc()
