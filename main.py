"""
Entry point — runs the web agent to log into the target application.
Usage:
    1. Copy .env.example to .env and set token + Excel path.
    2. python main.py
"""
import os
import json
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from agent import WebAgent
from excel_config import (
    load_hierarchy_configs_from_master_data,
    load_menu_target_from_sheet,
    load_named_table_rows_from_sheet,
    load_runtime_config_from_excel,
    load_sheet_rows_as_dicts,
    load_cross_hierarchy_configs_from_master_data,
)

# Keep shell-provided overrides (e.g., KEEP_OPEN=false for CI/non-interactive runs).
load_dotenv(override=False)

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
MODEL = os.environ.get("MODEL", "gpt-4o-mini")
APP_URL = os.environ.get("APP_URL", "http://dev1803.dev.e2open.com:9880/Main.action")
EXCEL_PATH = os.environ.get("EXCEL_PATH", "input.xlsx")
EXCEL_SHEET = os.environ.get("EXCEL_SHEET", "")
EXCEL_ROW_INDEX = int(os.environ.get("EXCEL_ROW_INDEX", "1"))
EXCEL_CREDENTIALS_SHEET = os.environ.get("EXCEL_CREDENTIALS_SHEET", "Credentials")
EXCEL_MENU_SHEET = os.environ.get("EXCEL_MENU_SHEET", "")
EXCEL_HIERARCHY_SHEET = os.environ.get("EXCEL_HIERARCHY_SHEET", "Hierarchy")
EXCEL_TARGET_SHEET = os.environ.get("EXCEL_TARGET_SHEET", "").strip()
KEEP_OPEN = os.environ.get("KEEP_OPEN", "true").strip().lower() in {"1", "true", "yes", "y"}

if not GITHUB_TOKEN.strip():
    raise ValueError("GITHUB_TOKEN is empty in .env")
if not EXCEL_PATH.strip():
    raise ValueError("EXCEL_PATH is empty in .env")

runtime = load_runtime_config_from_excel(
    file_path=EXCEL_PATH,
    sheet_name=EXCEL_CREDENTIALS_SHEET or EXCEL_SHEET or None,
    row_index=EXCEL_ROW_INDEX,
)

# Optional: drive left navigation from dedicated sheet names.
# EXCEL_MENU_SHEET -> parent menu group (e.g. Master data)
# EXCEL_TARGET_SHEET -> child menu item and workflow selector (e.g. Hierarchy, Attributes)
if EXCEL_MENU_SHEET.strip():
    runtime.menu_group = EXCEL_MENU_SHEET

if EXCEL_TARGET_SHEET:
    runtime.menu_item = EXCEL_TARGET_SHEET
elif EXCEL_MENU_SHEET.strip():
    runtime.menu_item = load_menu_target_from_sheet(EXCEL_PATH, EXCEL_MENU_SHEET)

target_sheet_name = EXCEL_TARGET_SHEET or EXCEL_HIERARCHY_SHEET
target_sheet_key = target_sheet_name.strip().lower()

target_rows = load_sheet_rows_as_dicts(EXCEL_PATH, target_sheet_name)
attributes_rows_master_data = load_named_table_rows_from_sheet(
    EXCEL_PATH,
    EXCEL_MENU_SHEET or "Master data",
    "Attribute Name",
)
attributes_rows_target_sheet = load_named_table_rows_from_sheet(
    EXCEL_PATH,
    EXCEL_TARGET_SHEET or "Attributes",
    "Attribute Name",
)

attributes_rows = attributes_rows_master_data or attributes_rows_target_sheet

master_data_hierarchy_configs = []
if target_sheet_key in {"hierarchy", "hierarchies"}:
    master_data_hierarchy_configs = load_hierarchy_configs_from_master_data(EXCEL_PATH, EXCEL_MENU_SHEET or "Master data")
elif runtime.menu_group and runtime.menu_group.lower() == "master data" and attributes_rows_master_data:
    # When Attributes are embedded in Master data, still load hierarchy blocks first.
    master_data_hierarchy_configs = load_hierarchy_configs_from_master_data(EXCEL_PATH, EXCEL_MENU_SHEET or "Master data")

# Load cross hierarchy configs
cross_hierarchy_configs = load_cross_hierarchy_configs_from_master_data(EXCEL_PATH, EXCEL_MENU_SHEET or "Master data")

has_customer_config = bool(runtime.customer_name and runtime.configuration_number)
has_menu_target = bool(runtime.menu_group and runtime.menu_item)
is_master_data_sequential = bool(
    runtime.menu_group
    and runtime.menu_group.lower() == "master data"
    and master_data_hierarchy_configs
    and attributes_rows
)

if not has_customer_config and not has_menu_target:
    raise ValueError(
        "Input file must include customer/config fields (customer_name + config_number), "
        "or menu navigation fields (menu_group + menu_item), or both."
    )

TASK = f"""
Navigate to {APP_URL} and log in with:
    - Username: {runtime.app_username}
    - Password: {runtime.app_password}

Steps:
1. Go to the URL.
2. Fill #Main_userid and #Main_password, then click #Main_submit.
   (Do NOT call get_page_content or wait_for_selector before these — just fill and click directly.)
3. Call get_page_content ONCE to confirm Cloud Studio title or URL change. Do NOT retry login.
"""

if has_customer_config:
    TASK += f"""

After successful login (customer/config flow):
4. Click #lnkConfigs to open Configuration Manager (do NOT call get_frames first).
5. Immediately call select_option_in_frame with:
   - frame_url_contains="ShowConfigurations"
   - selector="#customerDD"
   - label="{runtime.customer_name}"
    The tool handles whitespace and case automatically.
    If it fails, recover in this exact order:
    a. call get_frames
    b. retry select_option_in_frame with the same parameters
    c. if still failing, call get_select_options_in_frame for diagnostics and retry once more
    Do NOT attempt to click the dropdown first.
6. Open configuration "{runtime.configuration_number}" with open_configuration_read_only_in_frame using frame_url_contains="ShowConfigurations".
    - IMPORTANT: this must open the editable configuration, not view-only mode.
7. Call get_frames ONCE to confirm editable config is open.
"""

if has_menu_target and not is_master_data_sequential:
    TASK += f"""

After that (menu navigation flow):
9. Open left menu using open_left_menu_item with:
   - menu_group="{runtime.menu_group}"
   - menu_item="{runtime.menu_item}"
10. Confirm the final screen opened for "{runtime.menu_item}".
"""

# Master data sequential workflow (hierarchies + attributes + cross hierarchies) takes priority
if runtime.menu_group and runtime.menu_group.lower() == "master data" and master_data_hierarchy_configs and attributes_rows:
    TASK += f"""

=== MASTER DATA SEQUENTIAL AUTOMATION ===
Detected both hierarchy blocks and attributes rows in Excel.
Run in this EXACT order:

11. Open left menu using open_left_menu_item with:
   - menu_group="{runtime.menu_group}"
   - menu_item="Hierarchy"
12. Immediately after opening "Hierarchy", call configure_all_hierarchies with exactly this parameter.
    CRITICAL:
    - Execute exactly one step at a time; do not pre-open any later menu item.
    - Never call open_left_menu_item for two different menu_item values in the same iteration.
    - Do not call open_left_menu_item for "Attributes" before configure_all_hierarchies returns.
    - Do not call open_left_menu_item for "Cross Hierarchy" before configure_attributes_by_hierarchy returns.
    - Do not navigate away from the Hierarchy page while hierarchy configuration is running.
    - Wait for configure_all_hierarchies to finish and inspect its result first.
    - If any hierarchy has status ERROR, stop and report that error instead of continuing to Attributes.
    Do NOT call click_element_with_text separately:
    hierarchies = {json.dumps([{
    "hierarchy_name": cfg.hierarchy_name,
    "levels": [{"name": lvl.name, "visible": lvl.visible, "non_hierarchial": lvl.non_hierarchial} for lvl in cfg.levels]
} for cfg in master_data_hierarchy_configs])}
    The tool handles 'Add New' + form fill + save for each hierarchy automatically.
13. Only after configure_all_hierarchies succeeds for all hierarchies, open left menu using open_left_menu_item with:
   - menu_group="{runtime.menu_group}"
   - menu_item="Attributes"
14. Call configure_attributes_by_hierarchy with exactly this parameter:
    attributes_rows = {json.dumps(attributes_rows)}
    frame_url_contains = "attribute"
    The tool handles opening each hierarchy editor, filling all attribute fields, and saving.
    CRITICAL:
    - Wait for configure_attributes_by_hierarchy result before any further menu navigation.
    - Forbidden sequence: open_left_menu_item("Cross Hierarchy") before configure_attributes_by_hierarchy result.
"""
    
    if cross_hierarchy_configs:
        cross_h_rows = [{
            "attribute_name": cfg.attribute_name,
            "hierarchy_1_product": cfg.hierarchy_1_product,
            "hierarchy_2_channel": cfg.hierarchy_2_channel,
            "hierarchy_3_location": cfg.hierarchy_3_location,
            "attribute_type": cfg.attribute_type or "",
            "mapped_column": cfg.mapped_column or "",
            "editable": cfg.editable or ""
        } for cfg in cross_hierarchy_configs]
        TASK += f"""
15. Only after configure_attributes_by_hierarchy succeeds, open left menu using open_left_menu_item with:
   - menu_group="{runtime.menu_group}"
   - menu_item="Cross Hierarchy"
16. Call configure_cross_hierarchies with exactly this parameter:
    cross_hierarchy_rows = {json.dumps(cross_h_rows)}
    frame_url_contains = "hierarchy"
    The tool will fill each cross hierarchy attribute mapping with the specified hierarchy levels.
17. Report results and done.
"""
    else:
        TASK += """
15. Report results and done.
"""
# Fallback: old hierarchy-only workflow (no attributes)
elif runtime.menu_group and runtime.menu_item and runtime.menu_group.lower() == "master data" and target_sheet_key in {"hierarchy", "hierarchies"}:
    if master_data_hierarchy_configs:
        TASK += f"""

=== HIERARCHY FORM AUTOMATION ===
Excel Data to Fill: {len(master_data_hierarchy_configs)} hierarchies total
CRITICAL: All hierarchies must be configured. If one fails, diagnose and retry.
"""
        for idx, cfg in enumerate(master_data_hierarchy_configs, 1):
            levels_data = [
                {"name": lvl.name, "visible": lvl.visible, "non_hierarchial": lvl.non_hierarchial}
                for lvl in cfg.levels
            ]
            levels_str = json.dumps(levels_data)
            TASK += f"""
Hierarchy {idx}:
- Name: "{cfg.hierarchy_name}"
- Levels (in order): {levels_str}
  (each level has: name, visible=True means check Visible checkbox, non_hierarchial=True means check Non-Hierarchial checkbox)

{10 + idx}. Click "Add New" with click_element_with_text (exact_match=false).
   - If click fails, wait 1 second and retry.
{10 + idx + 1}. Immediately call configure_hierarchy_form with:
   - hierarchy_name="{cfg.hierarchy_name}"
   - levels={levels_str}
   - frame_url_contains="hierarchy.action"
   - This tool will fill the form, add all levels with their checkbox states from Excel, and save.
   - IMPORTANT: Watch the result message for "WARNING - Checkbox issues" which means checkboxes may not have been set correctly.
     If you see this warning, try running the command again or report it.
{10 + idx + 2}. If tool returns ERROR or multiple checkbox WARNINGs, perform diagnostic:
   a. Call get_frames to list all current frames
   b. Call get_page_content_in_frame on the "hierarchy.action" frame
   c. Look for whether a form dialog is open or if we're back at the list
   d. If form is still visible, try calling configure_hierarchy_form again with same parameters
   e. Report the full error message and diagnostic findings
{10 + idx + 3}. If tool succeeds, verify by checking get_page_content_in_frame shows "Hierarchy" list is back.
   - You should see table/list view, not a form.
"""
        
        TASK += """
Rules for all hierarchies:
- Use exact values from Excel only.
- Preserve level order exactly as provided.
- Each hierarchy MUST complete successfully before moving to the next one.
- If a hierarchy fails after multiple retries, report detailed error and STOP.
"""
    elif target_rows:
        TASK += f"""

Hierarchy configuration flow (fallback from sheet '{target_sheet_name}'):
11. Configure Hierarchy screen using EXACT values from these rows:
{json.dumps(target_rows, indent=2)}

Rules:
- Do NOT invent values.
- For each row, map column headers to visible form fields/labels and fill/select exactly.
- If a required UI field for a column cannot be found, report the row and column as error.
- Save/apply each row if the UI requires a submit/save action.
12. After processing, report each row as success/failure with reason.
"""
    else:
        TASK += f"""

Hierarchy configuration flow:
11. No hierarchy rows found in '{EXCEL_MENU_SHEET or "Master data"}' and none in '{target_sheet_name}'.
    Report this clearly and stop without making hierarchy changes.
"""
elif runtime.menu_group and runtime.menu_item and runtime.menu_group.lower() == "master data" and target_sheet_key in {"attribute", "attributes"}:
    if attributes_rows or target_rows:
        rows_for_attributes = attributes_rows or target_rows
        TASK += f"""

Attributes configuration flow (from sheet '{target_sheet_name}'):
11. Call configure_attributes_by_hierarchy exactly as below (pass the full list inline as attributes_rows):
    attributes_rows = {json.dumps(rows_for_attributes)}
    frame_url_contains = "attribute"
    The tool handles opening each hierarchy editor, filling all attribute fields, and saving.
12. Report per-hierarchy success/failure and final screen state.
"""
    else:
        TASK += f"""

Attributes configuration flow:
11. No attribute rows found in '{target_sheet_name}' or '{EXCEL_MENU_SHEET or "Master data"}'.
    Report this clearly and stop without making attribute changes.
"""

TASK += """

Report everything completed: login status, customer selected, configuration opened,
parent menu clicked, child menu clicked, and final URL/title/frame state.
"""


def _has_section_failure(text_lower: str, section_terms: list[str]) -> bool:
    terms = "|".join(section_terms)
    return bool(re.search(rf"(?:{terms}).{{0,120}}\b(error|failed|could not|unable)\b", text_lower, flags=re.DOTALL))


def _has_section_success(text_lower: str, success_patterns: list[str]) -> bool:
    return any(p in text_lower for p in success_patterns)


def _status_for_section(text_lower: str, section_terms: list[str], success_patterns: list[str]) -> str:
    if _has_section_failure(text_lower, section_terms):
        return "FAIL"
    if _has_section_success(text_lower, success_patterns):
        return "PASS"
    return "UNKNOWN"


def _write_run_summary(summary_text: str) -> None:
    text_lower = (summary_text or "").lower()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    overall_success = (
        "completed successfully" in text_lower
        or "no errors encountered" in text_lower
        or "without any errors" in text_lower
    )

    hierarchy_status = _status_for_section(
        text_lower,
        ["hierarch", "configure_all_hierarchies"],
        [
            "hierarchies configured successfully",
            "hierarchy configuration",
            "configure_all_hierarchies results: [{'hierarchy'",
            "status': 'ok'",
        ],
    )
    attributes_status = _status_for_section(
        text_lower,
        ["attribute", "configure_attributes_by_hierarchy"],
        [
            "configured attributes by hierarchy",
            "attributes configured",
            "attribute configuration",
            "all attributes",
        ],
    )
    cross_hierarchy_status = _status_for_section(
        text_lower,
        ["cross hierarch", "configure_cross_hierarchies"],
        [
            "configured cross hierarchies",
            "cross hierarchy configuration",
            "cross hierarchy mapping completed",
            "cross hierarchies configured successfully",
        ],
    )

    if overall_success:
        if hierarchy_status == "UNKNOWN":
            hierarchy_status = "PASS"
        if attributes_status == "UNKNOWN":
            attributes_status = "PASS"
        if cross_hierarchy_status == "UNKNOWN":
            cross_hierarchy_status = "PASS"

    expected_hierarchies = len(master_data_hierarchy_configs)
    expected_attributes = len(attributes_rows) if isinstance(attributes_rows, list) else 0
    expected_cross_rows = len(cross_hierarchy_configs)

    cross_group_counts: dict[tuple[str, str, str], int] = {}
    for cfg in cross_hierarchy_configs:
        key = (cfg.hierarchy_1_product, cfg.hierarchy_2_channel, cfg.hierarchy_3_location)
        cross_group_counts[key] = cross_group_counts.get(key, 0) + 1

    summary_md = Path("run_summary.md")
    summary_jsonl = Path("run_summary.jsonl")

    with summary_md.open("a", encoding="utf-8") as f:
        f.write(f"\n## Run Summary {timestamp}\n")
        f.write(f"- Hierarchy: {hierarchy_status} (expected rows: {expected_hierarchies})\n")
        f.write(f"- Attributes: {attributes_status} (expected rows: {expected_attributes})\n")
        f.write(f"- Cross Hierarchy: {cross_hierarchy_status} (expected rows: {expected_cross_rows})\n")
        if cross_group_counts:
            groups_rendered = ", ".join(
                [f"{p}/{c}/{l}={n}" for (p, c, l), n in cross_group_counts.items()]
            )
            f.write(f"- Cross Hierarchy groups: {groups_rendered}\n")
        f.write("\n")

    record = {
        "timestamp": timestamp,
        "hierarchy_status": hierarchy_status,
        "attributes_status": attributes_status,
        "cross_hierarchy_status": cross_hierarchy_status,
        "expected_hierarchies": expected_hierarchies,
        "expected_attributes": expected_attributes,
        "expected_cross_rows": expected_cross_rows,
        "cross_groups": [
            {
                "product": p,
                "channel": c,
                "location": l,
                "rows": n,
            }
            for (p, c, l), n in cross_group_counts.items()
        ],
    }
    with summary_jsonl.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True) + "\n")

if __name__ == "__main__":
    agent = WebAgent(
        github_token=GITHUB_TOKEN,
        model=MODEL,
        headless=False,   # set True to run without a visible browser window
        keep_open=KEEP_OPEN,   # set KEEP_OPEN=false in .env for non-interactive runs
    )
    summary = agent.run(TASK)
    print("\n=== Agent Summary ===")
    print(summary)
    _write_run_summary(summary)
    print("\n=== Run Summary Written ===")
    print("Saved: run_summary.md and run_summary.jsonl")
