# APP Simulation

Simple browser automation for APP configuration flows using Playwright and an LLM-driven web agent.

## What this project does

- Logs into the APP web UI
- Opens configuration manager
- Selects customer and configuration
- Navigates to menu targets
- Fills hierarchy data from Excel sheets

## Prerequisites

- Python 3.10+
- Git
- Network access to the target APP URL
- A GitHub personal access token (used by the agent runtime)

## Project files

- `main.py`: Entry point for the full automation flow
- `agent.py`: Agent orchestration and tool loop
- `browser_tools.py`: Playwright browser actions used by the agent
- `excel_config.py`: Reads runtime/menu/hierarchy config from Excel
- `.env.example`: Environment variable template
- `requirements.txt`: Python dependencies

## Setup

1. Clone the repository.
2. Create a virtual environment.
3. Install dependencies.
4. Install Playwright browser binaries.
5. Create your `.env` from `.env.example`.
6. Prepare your Excel input file.

### Windows PowerShell commands

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install
Copy-Item .env.example .env
```

## Environment variables

Update `.env` with values for your environment:

- `GITHUB_TOKEN`: GitHub PAT used by the agent
- `MODEL`: Model name (default in template is `gpt-4o-mini`)
- `APP_URL`: Target APP URL
- `EXCEL_PATH`: Path to input Excel file
- `EXCEL_CREDENTIALS_SHEET`: Sheet with login/customer/config fields
- `EXCEL_MENU_SHEET`: Sheet that defines menu target (example: `Master data`)
- `EXCEL_HIERARCHY_SHEET`: Sheet with hierarchy rows
- `KEEP_OPEN`: `true` or `false` to keep browser open after run

## Excel input expectations

The credentials/runtime sheet must provide values used by `main.py`, including:

- `app_username`
- `app_password`
- `customer_name`
- `config_number`

Hierarchy automation uses the hierarchy-related sheets configured in `.env`.

## Run automation

```powershell
python main.py
```

## Tests

Run available regression and flow tests directly:

```powershell
python test_hierarchy_checkbox_keyboard.py
python test_login_flow.py
python test_form_filling.py
```

## Troubleshooting

- If Playwright fails to launch a browser, run `playwright install` again.
- If login/navigation fails, verify `APP_URL` and credential values in Excel.
- If agent call fails, verify `GITHUB_TOKEN` and `MODEL` in `.env`.

## Notes for contributors

- Keep secrets out of git (`.env` is intentionally ignored).
- Put reusable config in `.env.example` and source files.
- Keep large local run logs out of commits unless needed for debugging.