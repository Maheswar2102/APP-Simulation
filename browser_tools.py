"""
Playwright browser tools exposed to the Claude agent via tool use.
Each function maps 1:1 to a tool that Claude can call.
"""
import base64
import os
from playwright.sync_api import Locator, Page

from excel_config import load_named_table_rows_from_sheet


def set_checkbox_state(locator: Locator, should_check: bool) -> bool:
    """Toggle checkbox state using keyboard interaction for ICEfaces-style controls."""
    before_state = locator.is_checked()
    if before_state != should_check:
        try:
            locator.focus()
            locator.press("Space", timeout=2_000)
        except Exception:
            locator.click(timeout=2_000, force=True)
    return locator.is_checked() == should_check


# ---------------------------------------------------------------------------
# Tool definitions (sent to Claude)
# ---------------------------------------------------------------------------
# OpenAI / GitHub-Models tool format  {"type": "function", "function": {...}}
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Navigate the browser to a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to navigate to"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_content",
            "description": (
                "Return the visible text and key form fields (inputs, buttons, links) "
                "from the current page so you can understand the page layout."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Take a screenshot of the current page and return it as a base64-encoded PNG.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click an element identified by a CSS selector or visible text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": (
                            "CSS selector, XPath (prefix with 'xpath='), "
                            "or visible text (prefix with 'text=')."
                        ),
                    }
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fill",
            "description": "Clear an input field and type a value into it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector or text= / xpath= locator for the input.",
                    },
                    "value": {"type": "string", "description": "Value to type into the field."},
                },
                "required": ["selector", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fill_in_frame",
            "description": "Clear an input field inside a specific iframe and type a value into it. Use this for fields with special characters in ID (like colons).",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the input field."},
                    "value": {"type": "string", "description": "Value to type into the field."},
                    "frame_index": {"type": "integer", "description": "Zero-based frame index."},
                    "frame_url_contains": {"type": "string", "description": "Substring of the frame URL to match."},
                },
                "required": ["selector", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a keyboard key (e.g. 'Enter', 'Tab', 'Escape').",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key name, e.g. 'Enter'."}
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait_for_selector",
            "description": "Wait until an element matching the CSS selector appears on the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to wait for."},
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Max wait time in milliseconds (default 10000).",
                    },
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_option",
            "description": (
                "Select an option from a <select> dropdown. Can match by visible label text, "
                "by value attribute, or by index (0-based). Prefer label matching."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the <select> element.",
                    },
                    "label": {
                        "type": "string",
                        "description": "Visible option text to select (preferred).",
                    },
                    "value": {
                        "type": "string",
                        "description": "Option value attribute to select (fallback).",
                    },
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_select_options",
            "description": "Return all available options (label + value) of a <select> dropdown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the <select> element.",
                    }
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_frames",
            "description": (
                "List all frames (iframes) on the current page. "
                "Returns each frame's name, URL, and index. "
                "Use this when page content appears to be inside an iframe."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_select_options_in_frame",
            "description": (
                "Return all <select> dropdowns and their options found inside a specific iframe. "
                "Provide either the frame URL substring or frame name to identify it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "frame_url_contains": {
                        "type": "string",
                        "description": "Substring of the frame's URL to match (e.g. 'orderEntry').",
                    },
                    "frame_name": {
                        "type": "string",
                        "description": "The name attribute of the iframe to target.",
                    },
                    "frame_index": {
                        "type": "integer",
                        "description": "Zero-based index of the frame from get_frames output.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_option_in_frame",
            "description": "Select an option in a <select> dropdown that is inside an iframe.",
            "parameters": {
                "type": "object",
                "properties": {
                    "frame_url_contains": {
                        "type": "string",
                        "description": "Substring of the frame URL to identify it.",
                    },
                    "frame_name": {
                        "type": "string",
                        "description": "Name attribute of the iframe.",
                    },
                    "frame_index": {
                        "type": "integer",
                        "description": "Zero-based index of the frame.",
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the <select> element inside the frame.",
                    },
                    "label": {
                        "type": "string",
                        "description": "Visible option text to select.",
                    },
                    "value": {
                        "type": "string",
                        "description": "Option value attribute to select (fallback).",
                    },
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_content_in_frame",
            "description": (
                "Return visible text, inputs, and buttons/icons from inside a specific iframe. "
                "Use this instead of get_page_content when content is inside an iframe."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "frame_url_contains": {"type": "string", "description": "Substring of the frame URL."},
                    "frame_name": {"type": "string", "description": "Name attribute of the iframe."},
                    "frame_index": {"type": "integer", "description": "Zero-based frame index."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_in_frame",
            "description": "Click an element inside a specific iframe using a CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the element to click."},
                    "frame_url_contains": {"type": "string", "description": "Substring of the frame URL."},
                    "frame_name": {"type": "string", "description": "Name attribute of the iframe."},
                    "frame_index": {"type": "integer", "description": "Zero-based frame index."},
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_rows_in_frame",
            "description": (
                "Return rows from a table inside an iframe, including cell text and clickable icons/actions per row. "
                "Use search_text to filter to rows containing a specific configuration number or name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "frame_url_contains": {"type": "string", "description": "Substring of the frame URL."},
                    "frame_name": {"type": "string", "description": "Name attribute of the iframe."},
                    "frame_index": {"type": "integer", "description": "Zero-based frame index."},
                    "table_selector": {"type": "string", "description": "CSS selector for the table (default: 'table')."},
                    "search_text": {"type": "string", "description": "Only return rows whose text contains this string (e.g. the configuration number)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_configuration_read_only_in_frame",
            "description": (
                "Find a configuration block/row inside an iframe by configuration number text like "
                "'Configuration No . <number>' and open it in editable mode. "
                "If the page only exposes a view icon, the tool should switch the underlying action to editable mode."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "configuration_number": {
                        "type": "string",
                        "description": "Configuration number to open, e.g. '5690'.",
                    },
                    "frame_url_contains": {"type": "string", "description": "Substring of the frame URL."},
                    "frame_name": {"type": "string", "description": "Name attribute of the iframe."},
                    "frame_index": {"type": "integer", "description": "Zero-based frame index."},
                },
                "required": ["configuration_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_left_menu_item",
            "description": (
                "Open a left navigation parent menu and then click its child item. "
                "Searches in the top page and all frames, and returns where clicks happened."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "menu_group": {"type": "string", "description": "Parent menu text, e.g. 'Master data'."},
                    "menu_item": {"type": "string", "description": "Child menu text, e.g. 'Hierarchy'."},
                },
                "required": ["menu_group", "menu_item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_element_with_text",
            "description": (
                "Search for and click a button or link by its visible text across all frames. "
                "Useful for clicking 'Add New', 'Save', 'Submit', etc. buttons without knowing their CSS selector."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Visible text of the button/link to click, e.g. 'Add New', 'Save', 'Submit'."
                    },
                    "exact_match": {
                        "type": "boolean",
                        "description": "If true, match text exactly (case-insensitive). If false, match substring."
                    }
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "configure_hierarchy_form",
            "description": (
                "Fill the Add Hierarchy Configuration form after clicking 'Add New'. "
                "Sets hierarchy name, adds levels with checkboxes in order, and clicks Save."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hierarchy_name": {
                        "type": "string",
                        "description": "Hierarchy Name value to fill."
                    },
                    "levels": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Level name"},
                                "visible": {"type": "boolean", "description": "Check the Visible checkbox if true"},
                                "non_hierarchial": {"type": "boolean", "description": "Check the Non-Hierarchial checkbox if true"}
                            },
                            "required": ["name"]
                        },
                        "description": "Level objects with name and checkbox flags (visible, non_hierarchial)."
                    },
                    "frame_url_contains": {
                        "type": "string",
                        "description": "Optional preferred frame URL fragment (default: 'hierarchy.action')."
                    }
                },
                "required": ["hierarchy_name", "levels"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "configure_all_hierarchies",
            "description": (
                "Configure all hierarchies in one call. For each hierarchy config, automatically clicks 'Add New' "
                "in the hierarchy list frame, then fills the form (name, levels, checkboxes) and saves. "
                "Use this instead of calling click+configure_hierarchy_form manually for each hierarchy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hierarchies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "hierarchy_name": {"type": "string"},
                                "levels": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "visible": {"type": "boolean"},
                                            "non_hierarchial": {"type": "boolean"}
                                        },
                                        "required": ["name"]
                                    }
                                }
                            },
                            "required": ["hierarchy_name", "levels"]
                        },
                        "description": "List of hierarchy configs to configure in sequence."
                    },
                    "frame_url_contains": {
                        "type": "string",
                        "description": "Optional preferred frame URL fragment (default: 'hierarchy.action')."
                    }
                },
                "required": ["hierarchies"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "configure_attributes_by_hierarchy",
            "description": (
                "On Master data > Attributes list, open each hierarchy row using the edit/pencil action, "
                "then add attributes from Excel rows and save each record. "
                "If attributes_rows is omitted, the tool auto-loads rows from EXCEL_PATH."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "attributes_rows": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Rows from Excel with headers such as Attribute Name, Hierarchy, Map To, Attribute Type, Editable.",
                    },
                    "frame_url_contains": {
                        "type": "string",
                        "description": "Preferred frame URL fragment for attributes pages (default: 'attribute').",
                    },
                },
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------
class BrowserTools:
    """Wraps a Playwright Page and executes tool calls from the Claude agent."""

    def __init__(self, page: Page):
        self.page = page

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """Dispatch a tool call and return a string result."""
        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            return f"ERROR: Unknown tool '{tool_name}'"
        try:
            return handler(**tool_input)
        except Exception as exc:  # noqa: BLE001
            return f"ERROR executing {tool_name}: {exc}"

    # ------------------------------------------------------------------
    # Individual tool implementations
    # ------------------------------------------------------------------

    def _tool_navigate(self, url: str) -> str:
        self.page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        return f"Navigated to {self.page.url}"

    def _tool_get_page_content(self) -> str:
        title = self.page.title()
        url = self.page.url

        # Collect visible inputs, buttons, links
        inputs = self.page.evaluate(
            """() => {
                const items = [];
                document.querySelectorAll('input, select, textarea').forEach(el => {
                    if (el.offsetParent !== null) {          // visible
                        items.push({
                            tag: el.tagName.toLowerCase(),
                            type: el.type || '',
                            name: el.name || '',
                            id: el.id || '',
                            placeholder: el.placeholder || '',
                            value: el.type === 'password' ? '***' : (el.value || ''),
                        });
                    }
                });
                return items;
            }"""
        )
        buttons = self.page.evaluate(
            """() => {
                const items = [];
                document.querySelectorAll('button, input[type=submit], input[type=button], a').forEach(el => {
                    if (el.offsetParent !== null) {
                        const text = (el.innerText || el.value || el.textContent || '').trim();
                        if (text) items.push({ tag: el.tagName.toLowerCase(), text });
                    }
                });
                return items.slice(0, 20);
            }"""
        )

        # Visible body text (trimmed)
        body_text = self.page.inner_text("body")[:1500]

        return (
            f"URL: {url}\nTitle: {title}\n\n"
            f"=== Inputs ===\n{inputs}\n\n"
            f"=== Buttons / Links ===\n{buttons}\n\n"
            f"=== Visible Text (truncated) ===\n{body_text}"
        )

    def _tool_screenshot(self) -> str:
        png_bytes = self.page.screenshot(full_page=False)
        return base64.b64encode(png_bytes).decode()

    def _tool_click(self, selector: str) -> str:
        self.page.click(selector, timeout=10_000)
        return f"Clicked '{selector}'"

    def _tool_fill(self, selector: str, value: str) -> str:
        self.page.fill(selector, value, timeout=10_000)
        return f"Filled '{selector}' with value"  # don't echo the value for security

    def _tool_fill_in_frame(self, selector: str, value: str, frame_index: int = None, frame_url_contains: str = None) -> str:
        """Fill an input field inside a specific frame."""
        frame = self._get_frame(frame_url_contains, None, frame_index)
        if frame is None:
            return "ERROR: Could not find matching frame. Use get_frames first."
        frame.fill(selector, value, timeout=10_000)
        return f"Filled '{selector}' in frame with value"

    def _tool_press_key(self, key: str) -> str:
        self.page.keyboard.press(key)
        return f"Pressed key '{key}'"

    def _tool_wait_for_selector(self, selector: str, timeout_ms: int = 10_000) -> str:
        self.page.wait_for_selector(selector, timeout=timeout_ms)
        return f"Element '{selector}' found on page"

    def _tool_select_option(self, selector: str, label: str = None, value: str = None) -> str:
        if label:
            self.page.select_option(selector, label=label, timeout=10_000)
            return f"Selected option with label '{label}' in '{selector}'"
        elif value:
            self.page.select_option(selector, value=value, timeout=10_000)
            return f"Selected option with value '{value}' in '{selector}'"
        else:
            return "ERROR: select_option requires either 'label' or 'value'"

    def _tool_get_select_options(self, selector: str) -> str:
        options = self.page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                return Array.from(el.options).map(o => ({
                    label: o.text.trim(),
                    value: o.value,
                    selected: o.selected,
                }));
            }""",
            selector,
        )
        if options is None:
            return f"ERROR: No <select> element found for selector '{selector}'"
        return str(options)

    def _get_frame(self, frame_url_contains: str = None, frame_name: str = None, frame_index: int = None):
        """Resolve a frame by URL substring, name, or index."""
        frames = self.page.frames
        if frame_index is not None:
            return frames[frame_index]
        if frame_name:
            return next((f for f in frames if f.name == frame_name), None)
        if frame_url_contains:
            # Prefer exact-case match first, then case-insensitive URL contains.
            exact = next((f for f in frames if frame_url_contains in (f.url or "")), None)
            if exact:
                return exact
            wanted = frame_url_contains.lower()
            return next((f for f in frames if wanted in (f.url or "").lower()), None)
        return None

    def _tool_get_frames(self) -> str:
        frames = self.page.frames
        result = []
        for i, f in enumerate(frames):
            result.append({"index": i, "name": f.name or "(no name)", "url": f.url})
        return str(result)

    def _tool_get_select_options_in_frame(
        self,
        frame_url_contains: str = None,
        frame_name: str = None,
        frame_index: int = None,
        selector: str = None,
    ) -> str:
        frame = self._get_frame(frame_url_contains, frame_name, frame_index)
        if frame is None:
            return "ERROR: Could not find matching frame. Use get_frames to list available frames."
        selects = frame.evaluate(
            """() => {
                const result = [];
                document.querySelectorAll('select').forEach(sel => {
                    result.push({
                        id: sel.id || '',
                        name: sel.name || '',
                        selector: sel.id ? '#' + sel.id : ('select[name="' + sel.name + '"]'),
                        options: Array.from(sel.options).map(o => ({
                            label: o.text.trim(),
                            label_raw: o.text,  // Include raw text for debugging whitespace issues
                            value: o.value,
                            selected: o.selected
                        }))
                    });
                });
                return result;
            }"""
        )
        if not selects:
            return f"No <select> elements found in frame '{frame.url}'"
        return str(selects)

    def _tool_select_option_in_frame(
        self,
        selector: str,
        frame_url_contains: str = None,
        frame_name: str = None,
        frame_index: int = None,
        label: str = None,
        value: str = None,
    ) -> str:
        if not label and not value:
            return "ERROR: select_option_in_frame requires either 'label' or 'value'"

        # Resolve frame with retry to handle post-login/config-manager load latency.
        frame = None
        for _ in range(10):
            try:
                frame = self._get_frame(frame_url_contains, frame_name, frame_index)
                if frame is not None:
                    break
            except Exception:
                pass
            self.page.wait_for_timeout(500)

        if frame is None:
            return "ERROR: Could not find matching frame after retries. Use get_frames to list available frames."

        # Wait for dropdown and at least one option to appear.
        try:
            frame.wait_for_selector(selector, timeout=12_000)
        except Exception as e:
            return f"ERROR: Selector '{selector}' not found in frame '{frame.url}': {str(e)[:140]}"

        options_ready = False
        for _ in range(12):
            try:
                count = frame.evaluate(
                    """(sel) => {
                        const el = document.querySelector(sel);
                        return el ? el.options.length : 0;
                    }""",
                    selector,
                )
                if isinstance(count, int) and count > 0:
                    options_ready = True
                    break
            except Exception:
                pass
            self.page.wait_for_timeout(350)

        if not options_ready:
            return f"ERROR: Dropdown '{selector}' is present but has no options in frame '{frame.url}'"

        if value:
            try:
                frame.select_option(selector, value=value, timeout=10_000)
                return f"Selected option with value '{value}' in frame '{frame.url}' selector '{selector}'"
            except Exception as e:
                return f"ERROR selecting value '{value}' in '{selector}': {str(e)[:180]}"

        # Label path: robust normalize + set value + dispatch change/input + verify selected text.
        try:
            result = frame.evaluate(
                r"""([sel, wanted]) => {
                    const el = document.querySelector(sel);
                    if (!el) return {ok: false, reason: 'NO_ELEMENT', options: []};

                    const normalize = (s) => (s || '')
                        .trim()
                        .toLowerCase()
                        .replace(/\u00a0/g, ' ')
                        .replace(/\s+/g, ' ');

                    const wantedNorm = normalize(wanted);
                    const opts = Array.from(el.options || []);
                    const optionTexts = opts.map(o => (o.text || '').trim());

                    if (!opts.length) {
                        return {ok: false, reason: 'NO_OPTIONS', options: optionTexts};
                    }

                    let target = opts.find(o => normalize(o.text) === wantedNorm)
                        || opts.find(o => normalize(o.text).includes(wantedNorm))
                        || opts.find(o => wantedNorm.includes(normalize(o.text)));

                    if (!target) {
                        const words = wantedNorm.split(' ').filter(Boolean);
                        target = opts.find(o => {
                            const txt = normalize(o.text);
                            return words.every(w => txt.includes(w));
                        });
                    }

                    if (!target) {
                        return {ok: false, reason: 'NO_MATCH', options: optionTexts};
                    }

                    el.value = target.value;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));

                    const selectedText = (el.options[el.selectedIndex]?.text || '').trim();
                    const verified = normalize(selectedText) === normalize(target.text)
                        || normalize(selectedText).includes(normalize(target.text));

                    return {
                        ok: verified,
                        reason: verified ? 'OK' : 'VERIFY_FAILED',
                        selectedText,
                        selectedValue: el.value,
                        matchedText: (target.text || '').trim(),
                        options: optionTexts,
                    };
                }""",
                [selector, label],
            )
        except Exception as e:
            return f"ERROR in select_option_in_frame evaluate path: {str(e)[:180]}"

        if result.get("ok"):
            return (
                f"Selected option with label '{label}' in frame '{frame.url}' selector '{selector}' "
                f"(matched='{result.get('matchedText', '')}', value='{result.get('selectedValue', '')}')"
            )

        return (
            f"ERROR executing select_option_in_frame: Could not select label '{label}' in selector '{selector}'. "
            f"Reason: {result.get('reason', 'UNKNOWN')}. Available options: {result.get('options', [])}"
        )

    def _tool_get_page_content_in_frame(
        self,
        frame_url_contains: str = None,
        frame_name: str = None,
        frame_index: int = None,
    ) -> str:
        frame = self._get_frame(frame_url_contains, frame_name, frame_index)
        if frame is None:
            return "ERROR: Could not find matching frame. Use get_frames first."
        url = frame.url
        inputs = frame.evaluate(
            """() => {
                const items = [];
                document.querySelectorAll('input, select, textarea').forEach(el => {
                    if (el.offsetParent !== null) {
                        items.push({
                            tag: el.tagName.toLowerCase(),
                            type: el.type || '',
                            name: el.name || '',
                            id: el.id || '',
                            placeholder: el.placeholder || '',
                        });
                    }
                });
                return items;
            }"""
        )
        buttons = frame.evaluate(
            """() => {
                const items = [];
                document.querySelectorAll('button, input[type=submit], input[type=button], a, img[onclick], img[title]').forEach(el => {
                    if (el.offsetParent !== null) {
                        const text = (el.innerText || el.value || el.title || el.alt || el.textContent || '').trim();
                        const onclick = el.getAttribute('onclick') || '';
                        if (text || onclick) {
                            items.push({
                                tag: el.tagName.toLowerCase(),
                                text: text.substring(0, 80),
                                id: el.id || '',
                                title: el.getAttribute('title') || '',
                                src: el.tagName === 'IMG' ? (el.src || '').split('/').pop() : '',
                                onclick: onclick.substring(0, 100),
                            });
                        }
                    }
                });
                return items.slice(0, 40);
            }"""
        )
        body_text = frame.inner_text("body")[:2000]
        return (
            f"Frame URL: {url}\n\n"
            f"=== Inputs ===\n{inputs}\n\n"
            f"=== Buttons / Icons / Links ===\n{buttons}\n\n"
            f"=== Visible Text (truncated) ===\n{body_text}"
        )

    def _tool_click_in_frame(
        self,
        selector: str,
        frame_url_contains: str = None,
        frame_name: str = None,
        frame_index: int = None,
    ) -> str:
        frame = self._get_frame(frame_url_contains, frame_name, frame_index)
        if frame is None:
            return "ERROR: Could not find matching frame. Use get_frames first."
        frame.click(selector, timeout=15_000)
        return f"Clicked '{selector}' in frame '{frame.url}'"

    def _tool_get_table_rows_in_frame(
        self,
        frame_url_contains: str = None,
        frame_name: str = None,
        frame_index: int = None,
        table_selector: str = "table",
        search_text: str = None,
    ) -> str:
        """Return table rows, optionally filtering to rows that contain search_text."""
        frame = self._get_frame(frame_url_contains, frame_name, frame_index)
        if frame is None:
            return "ERROR: Could not find matching frame. Use get_frames first."
        rows = frame.evaluate(
            """([tableSel, searchText]) => {
                const results = [];
                const tables = document.querySelectorAll(tableSel);
                tables.forEach((table, tIdx) => {
                    const rows = Array.from(table.querySelectorAll('tr'));
                    rows.forEach((row, rIdx) => {
                        const cellTexts = Array.from(row.querySelectorAll('td, th'))
                            .map(td => td.innerText.trim())
                            .filter(t => t.length > 0);
                        const rowText = cellTexts.join(' | ');
                        if (!searchText || rowText.toLowerCase().includes(searchText.toLowerCase())) {
                            // Collect clickable icons / links in this row
                            const actions = [];
                            row.querySelectorAll('a, img[onclick], img[title], button').forEach(el => {
                                const title = el.getAttribute('title') || el.getAttribute('alt') || el.innerText || '';
                                const onclick = el.getAttribute('onclick') || '';
                                const src = el.tagName === 'IMG' ? (el.src || '').split('/').pop() : '';
                                const id = el.id || '';
                                const cls = el.className || '';
                                if (title || onclick || src) {
                                    actions.push({ tag: el.tagName.toLowerCase(), title, src, onclick: onclick.substring(0, 120), id, cls });
                                }
                            });
                            results.push({ tableIndex: tIdx, rowIndex: rIdx, cells: cellTexts, actions });
                        }
                    });
                });
                return results.slice(0, 20);
            }""",
            [table_selector, search_text],
        )
        if not rows:
            hint = f" containing '{search_text}'" if search_text else ""
            return f"No rows found{hint} in '{table_selector}' inside frame '{frame.url}'"
        return str(rows)

    def _tool_open_configuration_read_only_in_frame(
        self,
        configuration_number: str,
        frame_url_contains: str = None,
        frame_name: str = None,
        frame_index: int = None,
    ) -> str:
        frame = self._get_frame(frame_url_contains, frame_name, frame_index)
        if frame is None:
            return "ERROR: Could not find matching frame. Use get_frames first."

        def _attempt_open() -> dict:
            return frame.evaluate(
            r"""(configNo) => {
                const normalize = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const configNorm = normalize(String(configNo));
                const candidates = Array.from(document.querySelectorAll('td, div, span, a, p, b, strong, label'));

                let anchor = null;
                for (const el of candidates) {
                    const txt = normalize(el.innerText || el.textContent || '');
                    if (!txt.includes(configNorm)) continue;
                    if (txt.includes('configuration no') || txt.includes('configuration no .') || txt.includes('configuration')) {
                        anchor = el;
                        break;
                    }
                }

                // Fallback: any element containing the config number
                if (!anchor) {
                    anchor = candidates.find(el => normalize(el.innerText || el.textContent || '').includes(configNorm)) || null;
                }

                if (!anchor) {
                    return { ok: false, message: `Configuration '${configNo}' not found in frame text.` };
                }

                const containers = [];
                const row = anchor.closest('tr');
                if (row) containers.push(row);
                if (row && row.nextElementSibling) containers.push(row.nextElementSibling);
                if (anchor.parentElement) containers.push(anchor.parentElement);
                if (anchor.parentElement && anchor.parentElement.parentElement) containers.push(anchor.parentElement.parentElement);
                const table = anchor.closest('table');
                if (table) containers.push(table);
                containers.push(document.body);

                const iconSelector = [
                    "img[title*='search' i]",
                    "img[title*='view' i]",
                    "img[title*='read' i]",
                    "img[alt*='search' i]",
                    "img[src*='search' i]",
                    "img[src*='view' i]",
                    "img[src*='magnif' i]",
                    "a[title*='search' i]",
                    "a[title*='view' i]",
                    "a[title*='read' i]",
                    "button[title*='search' i]",
                    "button[title*='view' i]"
                ].join(',');

                let icon = null;
                for (const c of containers) {
                    icon = c.querySelector(iconSelector);
                    if (icon) break;
                }

                if (!icon) {
                    return {
                        ok: false,
                        message: `Configuration '${configNo}' found but no read-only/search icon detected nearby.`
                    };
                }

                const onclick = icon.getAttribute('onclick') || '';
                const displayArgs = onclick.match(/dislayFormElements\((.*)\);?/i);

                if (displayArgs) {
                    try {
                        const parsed = Function(`return [${displayArgs[1]}];`)();
                        if (Array.isArray(parsed) && parsed.length >= 6) {
                            if (top && typeof top.openConfiguration === 'function') {
                                top.openConfiguration(parsed[0], parsed[1], false, parsed[3], parsed[4], parsed[5]);
                                return {
                                    ok: true,
                                    message: `Opened configuration '${configNo}' in editable mode via top.openConfiguration(false).`,
                                    iconTag: icon.tagName.toLowerCase(),
                                    iconTitle: icon.getAttribute('title') || icon.getAttribute('alt') || '',
                                    iconSrc: icon.tagName === 'IMG' ? (icon.getAttribute('src') || '') : '',
                                    iconId: icon.id || '',
                                    frameUrl: location.href,
                                    mode: 'editable',
                                };
                            }

                            if (typeof window.dislayFormElements === 'function') {
                                window.dislayFormElements(parsed[0], parsed[1], false, parsed[3], parsed[4], parsed[5]);
                                return {
                                    ok: true,
                                    message: `Opened configuration '${configNo}' in editable mode via dislayFormElements(false).`,
                                    iconTag: icon.tagName.toLowerCase(),
                                    iconTitle: icon.getAttribute('title') || icon.getAttribute('alt') || '',
                                    iconSrc: icon.tagName === 'IMG' ? (icon.getAttribute('src') || '') : '',
                                    iconId: icon.id || '',
                                    frameUrl: location.href,
                                    mode: 'editable',
                                };
                            }
                        }
                    } catch (e) {
                    }
                }

                if (/viewmode\s*=\s*true/i.test(onclick)) {
                    try {
                        const editableOnclick = onclick.replace(/viewmode\s*=\s*true/ig, 'viewMode=false');
                        Function(editableOnclick)();
                        return {
                            ok: true,
                            message: `Opened configuration '${configNo}' in editable mode by rewriting viewMode=true to false.`,
                            iconTag: icon.tagName.toLowerCase(),
                            iconTitle: icon.getAttribute('title') || icon.getAttribute('alt') || '',
                            iconSrc: icon.tagName === 'IMG' ? (icon.getAttribute('src') || '') : '',
                            iconId: icon.id || '',
                            frameUrl: location.href,
                            mode: 'editable',
                        };
                    } catch (e) {
                    }
                }

                icon.click();
                return {
                    ok: true,
                    message: `Clicked configuration icon for '${configNo}'.`,
                    iconTag: icon.tagName.toLowerCase(),
                    iconTitle: icon.getAttribute('title') || icon.getAttribute('alt') || '',
                    iconSrc: icon.tagName === 'IMG' ? (icon.getAttribute('src') || '') : '',
                    iconId: icon.id || '',
                    frameUrl: location.href,
                    mode: 'icon-click',
                };
            }""",
                configuration_number,
            )

        result = _attempt_open()
        if isinstance(result, dict) and result.get("ok"):
            return str(result)

        # Refresh grid and retry when configuration row is not yet visible.
        try:
            frame.select_option("#tagDD", value="ALL", timeout=2_000)
        except Exception:
            pass

        try:
            frame.evaluate(
                """() => {
                    const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const nodes = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"], span, div'));
                    let btn = nodes.find(el => norm(el.innerText || el.textContent || el.value || '') === 'show all');
                    if (!btn) btn = nodes.find(el => norm(el.innerText || el.textContent || el.value || '').includes('show all'));
                    if (!btn) btn = nodes.find(el => norm(el.innerText || el.textContent || el.value || '') === 'search');
                    if (!btn) btn = nodes.find(el => norm(el.innerText || el.textContent || el.value || '').includes('search'));
                    if (btn) btn.click();
                }"""
            )
        except Exception:
            pass

        self.page.wait_for_timeout(1500)
        result = _attempt_open()
        return str(result)

    def _click_text_in_frame(self, frame, text: str) -> bool:
        """Try multiple text-locator strategies in a frame."""
        try:
            loc = frame.get_by_text(text, exact=True)
            if loc.count() > 0:
                loc.first.click(timeout=2_000)
                return True
        except Exception:
            pass
        try:
            loc = frame.get_by_text(text, exact=False)
            if loc.count() > 0:
                loc.first.click(timeout=2_000)
                return True
        except Exception:
            pass
        # Fast JS fallback to avoid Playwright waiting on strict locators
        try:
            clicked = frame.evaluate(
                """(target) => {
                    const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const wanted = norm(target);
                    const nodes = Array.from(document.querySelectorAll('a, button, div, span, li, td, th, p, label'));
                    const visible = el => {
                        const style = window.getComputedStyle(el);
                        return style && style.visibility !== 'hidden' && style.display !== 'none';
                    };

                    let candidate = nodes.find(el => visible(el) && norm(el.textContent) === wanted);
                    if (!candidate) {
                        candidate = nodes.find(el => visible(el) && norm(el.textContent).includes(wanted));
                    }
                    if (!candidate) return false;
                    candidate.click();
                    return true;
                }""",
                text,
            )
            return bool(clicked)
        except Exception:
            return False

    def _tool_open_left_menu_item(self, menu_group: str, menu_item: str) -> str:
        """Open parent menu then child menu, searching main page + all frames."""
        clicked_group_in = None
        clicked_item_in = None

        # Search all frames including top page frame
        frames = self.page.frames

        # First click parent menu
        for idx, frame in enumerate(frames):
            if self._click_text_in_frame(frame, menu_group):
                clicked_group_in = f"frame_index={idx}, name={frame.name or '(no name)'}, url={frame.url}"
                break

        # Then click child menu (may be in same frame or another)
        for idx, frame in enumerate(frames):
            if self._click_text_in_frame(frame, menu_item):
                clicked_item_in = f"frame_index={idx}, name={frame.name or '(no name)'}, url={frame.url}"
                break

        if not clicked_group_in:
            return f"ERROR: Could not find/click parent menu '{menu_group}' in any frame/page."
        if not clicked_item_in:
            return (
                f"Parent menu '{menu_group}' clicked in {clicked_group_in}, "
                f"but child menu '{menu_item}' was not found/clicked."
            )

        return (
            f"Clicked parent menu '{menu_group}' in {clicked_group_in}; "
            f"clicked child menu '{menu_item}' in {clicked_item_in}."
        )

    def _tool_click_element_with_text(self, text: str, exact_match: bool = True) -> str:
        """Click a button/link/element by its visible text across all frames and main page."""
        frames = self.page.frames
        
        for idx, frame in enumerate(frames):
            try:
                # Try to use Playwright's get_by_text locator for exact match
                if exact_match:
                    element = frame.get_by_text(text, exact=True)
                    if element.is_visible():
                        element.click(timeout=5_000)
                        return f"Clicked element with text '{text}' (exact match) in frame {idx} ({frame.url})"
                else:
                    # Try substring match
                    element = frame.get_by_text(text, exact=False)
                    if element.is_visible():
                        element.click(timeout=5_000)
                        return f"Clicked element with text '{text}' (substring match) in frame {idx} ({frame.url})"
            except Exception:
                continue
        
        # If exact match failed, try case-insensitive partial match using JavaScript
        for idx, frame in enumerate(frames):
            try:
                found = frame.evaluate(
                    """(searchText) => {
                        const normalizeText = (s) => (s || '').trim().replace(/\\s+/g, ' ').toLowerCase();
                        const wanted = normalizeText(searchText);
                        
                        // Find clickable elements (buttons, links, divs with click handlers, etc.)
                        const candidates = Array.from(document.querySelectorAll('button, a, div, span, label, [role="button"]'));
                        
                        for (const el of candidates) {
                            const elText = normalizeText(el.innerText || el.textContent || '');
                            if (elText === wanted || elText.includes(wanted)) {
                                const style = window.getComputedStyle(el);
                                if (style.display !== 'none' && style.visibility !== 'hidden') {
                                    try {
                                        el.click();
                                        return true;
                                    } catch (e) {
                                        // Try dispatchEvent as fallback
                                        el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                                        return true;
                                    }
                                }
                            }
                        }
                        return false;
                    }""",
                    text,
                )
                if found:
                    return f"Clicked element with text '{text}' in frame {idx} ({frame.url})"
            except Exception:
                continue
        
        return f"ERROR: Could not find or click element with text '{text}' in any frame or on main page."

    def _tool_configure_hierarchy_form(
        self,
        hierarchy_name: str,
        levels: list,
        frame_url_contains: str = "hierarchy.action",
    ) -> str:
        """Fill Add Hierarchy Configuration form with name, levels and per-level checkboxes, then Save."""
        # Normalise levels: accept both plain strings and dicts
        def _as_level_dict(lvl):
            if isinstance(lvl, dict):
                return {"name": str(lvl.get("name", "")).strip(), "visible": bool(lvl.get("visible", True)), "non_hierarchial": bool(lvl.get("non_hierarchial", False))}
            return {"name": str(lvl).strip(), "visible": True, "non_hierarchial": False}
        levels = [_as_level_dict(l) for l in levels]
        if not hierarchy_name or not str(hierarchy_name).strip():
            return "ERROR: hierarchy_name is required"
        if not isinstance(levels, list) or not levels:
            return "ERROR: levels must be a non-empty list"

        # Prefer requested frame first, then any frame containing hierarchy form inputs.
        frame = self._get_frame(frame_url_contains=frame_url_contains)
        if frame is None:
            for f in self.page.frames:
                try:
                    has_form = f.evaluate(
                        """() => !!(
                            document.querySelector("input[name='hierarchyForm:name']") ||
                            document.querySelector("input[id='hierarchyForm:name']") ||
                            document.querySelector("input[name*='hierarchyForm'][name*='name']")
                        )"""
                    )
                    if has_form:
                        frame = f
                        break
                except Exception:
                    continue

        if frame is None:
            return (
                "ERROR: Could not locate hierarchy form frame. "
                "Click 'Add New' first, then call configure_hierarchy_form."
            )

        # Fill hierarchy name field.
        name_selectors = [
            "input[name='hierarchyForm:name']",
            "input[id='hierarchyForm:name']",
            "input[name='name']",
            "input[id='name']",
        ]

        name_filled = False
        for sel in name_selectors:
            try:
                frame.fill(sel, str(hierarchy_name), timeout=3_000)
                name_filled = True
                break
            except Exception:
                continue

        if not name_filled:
            name_filled = bool(
                frame.evaluate(
                    """(val) => {
                        const candidates = Array.from(document.querySelectorAll("input[type='text']"));
                        if (!candidates.length) return false;
                        const target = candidates.find(el => {
                            const n = (el.name || '').toLowerCase();
                            const i = (el.id || '').toLowerCase();
                            return n.includes('hierarchyform:name') || i.includes('hierarchyform:name') || n === 'name' || i === 'name';
                        }) || candidates[0];
                        target.focus();
                        target.value = val;
                        target.dispatchEvent(new Event('input', { bubbles: true }));
                        target.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }""",
                    str(hierarchy_name),
                )
            )

        if not name_filled:
            return f"ERROR: Could not fill hierarchy name field in frame '{frame.url}'"

        def _wait_ms(ms: int) -> None:
            try:
                self.page.wait_for_timeout(ms)
            except Exception:
                try:
                    frame.evaluate(f"() => new Promise(r => setTimeout(r, {ms}))")
                except Exception:
                    pass

        def _get_level_editor_state() -> dict:
            return frame.evaluate(
                r"""() => {
                    const normalize = (s) => (s || '').replace(/\s+/g, ' ').trim();
                    const isVisible = (el) => {
                        if (!el) return false;
                        const st = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return st && st.display !== 'none' && st.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };

                    const levelInput = document.querySelector(
                        "input[name='hierarchyForm:levelName'], input[id='hierarchyForm:levelName'], input[name='levelName'], input[id='levelName']"
                    );
                    const levelTop = levelInput ? levelInput.getBoundingClientRect().top : null;

                    const allCheckboxes = Array.from(document.querySelectorAll("input[type='checkbox']")).map((el, idx) => {
                        const rect = el.getBoundingClientRect();
                        return {
                            index: idx,
                            name: el.name || '',
                            id: el.id || '',
                            checked: !!el.checked,
                            top: rect.top,
                            left: rect.left,
                            visible: isVisible(el),
                        };
                    });

                    const rowCheckboxes = levelTop == null
                        ? []
                        : allCheckboxes
                            .filter(cb => cb.visible && Math.abs(cb.top - levelTop) <= 28)
                            .sort((a, b) => a.left - b.left);

                    const rowTexts = Array.from(document.querySelectorAll('tr'))
                        .map(tr => normalize(tr.innerText || tr.textContent || ''))
                        .filter(text => /level\s+\d+/i.test(text));

                    return {
                        rowCount: rowTexts.length,
                        rowTexts,
                        rowCheckboxes,
                        allCheckboxes: allCheckboxes.slice(0, 12),
                    };
                }"""
            )

        def _click_button_with_text(target_text: str) -> bool:
            return bool(
                frame.evaluate(
                    r"""(wantedText) => {
                        const isVisible = (el) => {
                            const st = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return st && st.display !== 'none' && st.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                        };
                        const wanted = (wantedText || '').trim().toLowerCase();
                        const buttons = Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit'], a"));
                        let match = buttons.find(el => isVisible(el) && ((el.innerText || el.value || el.textContent || '').trim().toLowerCase() === wanted));
                        if (!match) {
                            match = buttons.find(el => isVisible(el) && ((el.innerText || el.value || el.textContent || '').trim().toLowerCase().includes(wanted)));
                        }
                        if (!match) return false;
                        match.click();
                        return true;
                    }""",
                    target_text,
                )
            )

        # Small delay after filling name to ensure form is ready for level inputs
        _wait_ms(200)

        # Add each level in order.
        added_levels = []
        checkbox_issues_overall = []
        for lvl_obj in levels:
            level_value = lvl_obj["name"]
            if not level_value:
                continue

            # STEP 1: Fill level name
            level_selectors = [
                "input[name='hierarchyForm:levelName']",
                "input[id='hierarchyForm:levelName']",
                "input[name='levelName']",
                "input[id='levelName']",
            ]

            level_filled = False
            for sel in level_selectors:
                try:
                    frame.fill(sel, level_value, timeout=3_000)
                    level_filled = True
                    break
                except Exception:
                    continue

            if not level_filled:
                level_filled = bool(
                    frame.evaluate(
                        """(val) => {
                            const candidates = Array.from(document.querySelectorAll("input[type='text']"));
                            if (!candidates.length) return false;
                            const target = candidates.find(el => {
                                const n = (el.name || '').toLowerCase();
                                const i = (el.id || '').toLowerCase();
                                return n.includes('levelname') || i.includes('levelname');
                            }) || candidates[candidates.length - 1];
                            target.focus();
                            target.value = val;
                            target.dispatchEvent(new Event('input', { bubbles: true }));
                            target.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }""",
                        level_value,
                    )
                )

            if not level_filled:
                return f"ERROR: Could not fill level input for '{level_value}'"

            # STEP 2: Wait for form to be ready for checkbox interaction
            _wait_ms(300)
            state_before = _get_level_editor_state()
            before_row_count = int(state_before.get("rowCount", 0))

            # STEP 3: Handle checkboxes BEFORE clicking Add
            # Only use the two checkboxes aligned with the level input row.
            def _set_checkbox(checkbox_kind: str, should_check: bool) -> tuple[bool, str]:
                try:
                    current_state = _get_level_editor_state()
                    row_checkboxes = current_state.get("rowCheckboxes", [])
                    target_pos = 0 if checkbox_kind == "visible" else 1

                    if len(row_checkboxes) <= target_pos:
                        return False, (
                            f"LEVEL_ROW_CHECKBOX_NOT_FOUND: kind={checkbox_kind}, "
                            f"rowCheckboxes={row_checkboxes}, allCheckboxes={current_state.get('allCheckboxes', [])}"
                        )

                    target = row_checkboxes[target_pos]
                    locator = frame.locator("input[type='checkbox']").nth(int(target["index"]))
                    before_state = locator.is_checked()
                    success = set_checkbox_state(locator, should_check)

                    _wait_ms(100)
                    after_state = locator.is_checked()
                    status = f"{checkbox_kind}: {before_state} -> {after_state} (target={should_check})"
                    return success, status
                except Exception as e:
                    return False, str(e)

            visible_ok, visible_msg = _set_checkbox("visible", lvl_obj["visible"])
            non_hier_ok, non_hier_msg = _set_checkbox("non_hierarch", lvl_obj["non_hierarchial"])

            # Build checkbox diagnostic message for this level
            checkbox_diagnostic = []
            if not visible_ok:
                checkbox_diagnostic.append(f"Visible: {visible_msg}")
            else:
                checkbox_diagnostic.append(f"Visible: ✓ {visible_msg}")
            if not non_hier_ok:
                checkbox_diagnostic.append(f"NonHierarch: {non_hier_msg}")
            else:
                checkbox_diagnostic.append(f"NonHierarch: ✓ {non_hier_msg}")
            
            checkbox_issues = "; ".join(checkbox_diagnostic)
            if not visible_ok or not non_hier_ok:
                checkbox_issues_overall.append(f"Level '{level_value}': {checkbox_issues}")

            # STEP 4: Wait a bit more before clicking Add (ensure checkboxes are fully registered)
            _wait_ms(250)

            # STEP 5: Click the "Add" button to add this level
            add_clicked = _click_button_with_text("add")

            if not add_clicked:
                # More detailed error: report what buttons are visible
                button_info = frame.evaluate(
                    """() => {
                        const buttons = Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit'], a"));
                        return buttons.map(b => ({
                            text: (b.innerText || b.value || b.textContent || '').trim().slice(0, 50),
                            tag: b.tagName.toLowerCase(),
                            visible: window.getComputedStyle(b).display !== 'none'
                        })).slice(0, 5);
                    }"""
                )
                return f"ERROR: Could not click Add button for level '{level_value}'. Available buttons: {button_info}"

            level_added = False
            last_state = state_before
            for _ in range(8):
                _wait_ms(250)
                last_state = _get_level_editor_state()
                row_count = int(last_state.get("rowCount", 0))
                row_texts = " || ".join(last_state.get("rowTexts", []))
                if row_count >= before_row_count + 1 and level_value.lower() in row_texts.lower():
                    level_added = True
                    break

            if not level_added:
                add_clicked_retry = _click_button_with_text("add")
                if add_clicked_retry:
                    for _ in range(8):
                        _wait_ms(250)
                        last_state = _get_level_editor_state()
                        row_count = int(last_state.get("rowCount", 0))
                        row_texts = " || ".join(last_state.get("rowTexts", []))
                        if row_count >= before_row_count + 1 and level_value.lower() in row_texts.lower():
                            level_added = True
                            break

            if not level_added:
                return (
                    f"ERROR: Add did not persist level '{level_value}'. "
                    f"rowCountBefore={before_row_count}, rowCountAfter={last_state.get('rowCount')}, "
                    f"rows={last_state.get('rowTexts', [])}, checkbox_state={checkbox_issues}"
                )

            # Track level with optional checkbox diagnostic info
            level_entry = {"name": level_value, "visible": lvl_obj["visible"], "non_hierarchial": lvl_obj["non_hierarchial"]}
            if not visible_ok or not non_hier_ok:
                level_entry["checkbox_issues"] = checkbox_issues
            added_levels.append(level_entry)

        # Click Save.
        # First add a small delay to ensure all form updates are complete
        _wait_ms(500)

        save_clicked = _click_button_with_text("save")

        if not save_clicked:
            # Try to get diagnostic info on available buttons
            button_info = frame.evaluate(
                """() => {
                    const buttons = Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit'], a"));
                    return buttons.map(b => ({
                        text: (b.innerText || b.value || b.textContent || '').trim().slice(0, 50),
                        tag: b.tagName.toLowerCase(),
                        visible: window.getComputedStyle(b).display !== 'none'
                    })).slice(0, 5);
                }"""
            )
            error_msg = f"ERROR: Could not click Save button. Added {len(added_levels)} levels. Available buttons: {button_info}"
            if checkbox_issues_overall:
                error_msg += f" [Also had {len(checkbox_issues_overall)} checkbox issues]"
            return error_msg

        # Wait a moment for form to close/postback to complete
        _wait_ms(400)

        result_msg = (
            f"Configured hierarchy form in frame '{frame.url}': "
            f"hierarchy_name='{hierarchy_name}', added_levels={added_levels}, save_clicked=True"
        )
        
        # Include checkbox issues as a warning if any occurred (concise format)
        if checkbox_issues_overall:
            result_msg += f" [WARNING: {len(checkbox_issues_overall)} level(s) had checkbox matching issues]"
        
        return result_msg

    def _tool_configure_all_hierarchies(
        self,
        hierarchies: list,
        frame_url_contains: str = "hierarchy.action",
    ) -> str:
        """Configure multiple hierarchies sequentially.

        For each hierarchy: re-acquires the frame fresh, clicks Add New, fills form, saves.
        Re-acquiring the frame each time handles the frame reload that happens after each Save.
        """
        if not isinstance(hierarchies, list) or not hierarchies:
            return "ERROR: hierarchies must be a non-empty list"

        def _fresh_hierarchy_frame():
            """Always return a live (non-detached) frame matching frame_url_contains."""
            for f in self.page.frames:
                try:
                    furl = (f.url or "").lower()
                    if frame_url_contains.lower() in furl or "hierarchy" in furl:
                        # Probe that the frame is alive
                        _ = f.evaluate("() => document.readyState")
                        # Prefer frames that actually contain hierarchy list/form content.
                        has_hierarchy_ui = f.evaluate(
                            """() => {
                                const txt = (document.body?.innerText || '').toLowerCase();
                                return txt.includes('hierarchy') ||
                                       !!document.querySelector("input[name='hierarchyForm:name'], input[id='hierarchyForm:name']");
                            }"""
                        )
                        if not has_hierarchy_ui:
                            continue
                        return f
                except Exception:
                    continue
            return None

        def _click_add_new() -> bool:
            """Click 'Add New' in the hierarchy frame, or any visible frame."""
            # Try dedicated hierarchy frame first
            hf = _fresh_hierarchy_frame()
            if hf:
                try:
                    ok = hf.evaluate(
                        r"""() => {
                            const norm = s => (s||'').replace(/\s+/g,' ').trim().toLowerCase();
                            const btn = [...document.querySelectorAll('a,button,input[type=submit],input[type=button]')]
                                .find(el => norm(el.innerText||el.value||'') === 'add new'
                                         || norm(el.innerText||el.value||'').includes('add new'));
                            if (btn) { btn.click(); return true; }
                            return false;
                        }"""
                    )
                    if ok:
                        return True
                except Exception:
                    pass

            # Fallback: scan only hierarchy-like live frames (avoid ShowConfigurations misclicks)
            for f in self.page.frames:
                try:
                    furl = (f.url or "").lower()
                    if "hierarchy" not in furl:
                        txt = f.evaluate("() => (document.body?.innerText || '').toLowerCase().slice(0, 5000)")
                        if "hierarchy" not in txt:
                            continue
                    ok = f.evaluate(
                        r"""() => {
                            const norm = s => (s||'').replace(/\s+/g,' ').trim().toLowerCase();
                            const btn = [...document.querySelectorAll('a,button,input[type=submit],input[type=button]')]
                                .find(el => {
                                    const t = norm(el.innerText||el.value||'');
                                    return t === 'add new' || t.includes('add new');
                                });
                            if (btn) { btn.click(); return true; }
                            return false;
                        }"""
                    )
                    if ok:
                        return True
                except Exception:
                    continue
            return False

        results = []
        for cfg in hierarchies:
            if not isinstance(cfg, dict):
                results.append({"hierarchy": str(cfg), "status": "ERROR", "reason": "Config item is not a dict"})
                continue
            name = cfg.get("hierarchy_name") or cfg.get("name", "")
            levels = cfg.get("levels", [])
            if not name:
                results.append({"hierarchy": "(unknown)", "status": "ERROR", "reason": "Missing hierarchy_name"})
                continue

            # Wait a beat for any previous save to settle, then click Add New
            self.page.wait_for_timeout(800)
            add_clicked = _click_add_new()
            if not add_clicked:
                results.append({"hierarchy": name, "status": "ERROR", "reason": "Could not click 'Add New' button"})
                continue

            self.page.wait_for_timeout(1200)

            # Fill and save the hierarchy form
            form_result = "ERROR: hierarchy form not attempted"
            for attempt in range(1, 3):
                try:
                    form_result = self._tool_configure_hierarchy_form(name, levels, frame_url_contains)
                except Exception as e:
                    form_result = f"ERROR: {e}"

                # If the dialog did not appear yet, click Add New again and retry once.
                if "Could not locate hierarchy form frame" in form_result and attempt == 1:
                    self.page.wait_for_timeout(700)
                    _click_add_new()
                    self.page.wait_for_timeout(1200)
                    continue
                break

            if "ERROR" in form_result:
                results.append({"hierarchy": name, "status": "ERROR", "reason": form_result[:200]})
            else:
                results.append({"hierarchy": name, "status": "OK", "detail": form_result[:150]})

        return f"configure_all_hierarchies results: {results}"

    def _tool_configure_attributes_by_hierarchy(
        self,
        attributes_rows: list | None = None,
        frame_url_contains: str = "attribute",
    ) -> str:
        """Configure Attributes by opening each hierarchy row (pencil/edit), then adding attribute rows.

        The Attributes list page and editor both live in the same hierarchyAttribute.action frame.
        After clicking the pencil icon the frame content switches to the editor form.
        Fields: Attribute Name (text input), Map To (1st select), Attribute Type (2nd select),
        Editable (checkbox).  Each row is committed with the 'Add' submit button.
        All rows for one hierarchy are committed with the 'Save' submit button.
        """
        if not isinstance(attributes_rows, list) or not attributes_rows:
            excel_path = os.environ.get("EXCEL_PATH", "").strip() or "Test Documentxl.xlsx"
            master_data_sheet = os.environ.get("EXCEL_MENU_SHEET", "Master data").strip() or "Master data"
            target_sheet = os.environ.get("EXCEL_TARGET_SHEET", "Attributes").strip() or "Attributes"

            try:
                rows_master = load_named_table_rows_from_sheet(excel_path, master_data_sheet, "Attribute Name")
                rows_target = load_named_table_rows_from_sheet(excel_path, target_sheet, "Attribute Name")
                attributes_rows = rows_master or rows_target
            except Exception as e:
                return f"ERROR: attributes_rows missing and auto-load failed: {e}"

            if not isinstance(attributes_rows, list) or not attributes_rows:
                return (
                    "ERROR: attributes_rows missing and auto-load found no attribute rows "
                    f"(excel='{excel_path}', sheets tried: '{master_data_sheet}', '{target_sheet}')."
                )

        def _norm(s: str) -> str:
            return (s or "").strip().lower().replace(" ", "")

        def _get_row_val(row: dict, aliases: list) -> str:
            if not isinstance(row, dict):
                return ""
            for k, v in row.items():
                nk = _norm(str(k))
                if nk in aliases:
                    return "" if v is None else str(v).strip()
            return ""

        def _find_list_frame():
            # Prefer the dedicated hierarchyAttribute frame; fall back to any URL with 'attribute'.
            for f in self.page.frames:
                if "hierarchyAttribute" in (f.url or ""):
                    return f
            preferred = [
                f for f in self.page.frames
                if frame_url_contains.lower() in (f.url or "").lower()
            ]
            # Pick the one that actually shows the hierarchy-list table.
            for f in (preferred or self.page.frames):
                try:
                    has_list = f.evaluate(
                        """() => {
                            const txt = (document.body?.innerText || '').toLowerCase();
                            return txt.includes('hierarchy name') && txt.includes('actions');
                        }"""
                    )
                    if has_list:
                        return f
                except Exception:
                    continue
            return preferred[0] if preferred else None

        def _wait_for_attributes_list(max_tries: int = 20, delay_ms: int = 400):
            """Wait for Attributes list frame/table to become available after menu navigation."""
            last_frame = None
            for _ in range(max_tries):
                lf = _find_list_frame()
                if lf is not None:
                    last_frame = lf
                    try:
                        ready = lf.evaluate(
                            """() => {
                                const txt = (document.body?.innerText || '').toLowerCase();
                                const hasListText = txt.includes('hierarchy name') && txt.includes('actions');
                                const hasRows = document.querySelectorAll('tr').length > 1;
                                const hasEditActions = !!document.querySelector(
                                    "a[id*='hierarchyAttributeTable'], a[title*='edit' i], img[src*='edit' i], img[alt*='edit' i]"
                                );
                                return (hasListText && hasRows) || hasEditActions;
                            }"""
                        )
                        if ready:
                            return lf
                    except Exception:
                        pass
                self.page.wait_for_timeout(delay_ms)
            return last_frame

        def _open_hierarchy_editor(list_frame, hierarchy_name: str) -> bool:
            """Click the edit/pencil link for *hierarchy_name* in the list frame."""
            try:
                clicked = list_frame.evaluate(
                    r"""(targetName) => {
                        const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                        const wanted = norm(targetName);
                        const rows = Array.from(document.querySelectorAll('tr'));

                        const getRowHierarchyText = (row) => {
                            const tds = Array.from(row.querySelectorAll('td'));
                            if (!tds.length) return '';
                            // Prefer non-action cells for hierarchy name matching.
                            for (const td of tds) {
                                const txt = norm(td.innerText || td.textContent || '');
                                const hasAction = !!td.querySelector('a, button, img, input[type="image"]');
                                if (txt && !hasAction) return txt;
                            }
                            return norm(tds[0].innerText || tds[0].textContent || '');
                        };

                        const clickRowEdit = (row) => {
                            let btn = row.querySelector(
                                "a[id*='hierarchyAttributeTable'] img, " +
                                "a[id*='hierarchyAttributeTable'], " +
                                "a[title*='edit' i], a[aria-label*='edit' i], " +
                                "img[src*='edit' i], img[alt*='Edit' i], img[title*='edit' i], " +
                                "img[src*='pencil' i]"
                            );
                            if (!btn) {
                                // Prefer action column link/button if present
                                const tds = Array.from(row.querySelectorAll('td'));
                                const lastTd = tds.length ? tds[tds.length - 1] : null;
                                if (lastTd) {
                                    btn = lastTd.querySelector("a, button, img");
                                }
                            }
                            if (!btn) btn = row.querySelector("a img, a, button");
                            if (!btn) return false;
                            const clickable = btn.closest('a, button') || btn;
                            clickable.click();
                            return true;
                        };

                        // Pass 1: exact hierarchy name match.
                        for (const row of rows) {
                            const hText = getRowHierarchyText(row);
                            if (!hText) continue;
                            if (hText === wanted && clickRowEdit(row)) return true;
                        }

                        // Pass 2: fallback to contains match.
                        for (const row of rows) {
                            const hText = getRowHierarchyText(row);
                            if (!hText) continue;
                            if ((hText.includes(wanted) || wanted.includes(hText)) && clickRowEdit(row)) return true;
                        }

                        return false;
                    }""",
                    hierarchy_name,
                )
                return bool(clicked)
            except Exception:
                return False

        def _fill_attr_row(editor_frame, attr_name: str, map_to: str, attr_type: str, editable: str) -> tuple[bool, str]:
            """Fill the attribute form fields in the editor and click Add."""
            # 1) Attribute Name — use JS to set value + fire ICEfaces events
            try:
                ok = editor_frame.evaluate(
                    r"""([val]) => {
                        const inp = document.querySelector('input[name$="attributeName"], input[id$="attributeName"]');
                        if (!inp) return false;
                        inp.focus();
                        inp.value = val;
                        inp.dispatchEvent(new Event('input',  {bubbles: true}));
                        inp.dispatchEvent(new Event('change', {bubbles: true}));
                        inp.blur();
                        return true;
                    }""",
                    [attr_name],
                )
                if not ok:
                    return False, "Attribute Name input not found"
            except Exception as e:
                return False, f"Attribute Name fill error: {e}"

            # 2) Map To — first <select> in the form
            if map_to and map_to.lower() not in ("", "select"):
                try:
                    editor_frame.evaluate(
                        r"""([val]) => {
                            const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                            const wanted = norm(val);
                            const selects = document.querySelectorAll('select');
                            for (const sel of selects) {
                                const opt = Array.from(sel.options).find(o => norm(o.text) === wanted)
                                          || Array.from(sel.options).find(o => norm(o.text).includes(wanted));
                                if (opt) {
                                    sel.value = opt.value;
                                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                                    return true;
                                }
                            }
                            return false;
                        }""",
                        [map_to],
                    )
                except Exception:
                    pass  # Map To is optional

            # 3) Attribute Type — select whose options include Integer/String/Date/Numeric
            if attr_type:
                try:
                    ok = editor_frame.evaluate(
                        r"""([val]) => {
                            const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                            const wanted = norm(val);
                            const typeOptions = ['integer', 'string', 'date', 'numeric'];
                            const selects = document.querySelectorAll('select');
                            for (const sel of selects) {
                                const opts = Array.from(sel.options).map(o => norm(o.text));
                                if (!opts.some(t => typeOptions.includes(t))) continue;
                                const opt = Array.from(sel.options).find(o => norm(o.text) === wanted)
                                          || Array.from(sel.options).find(o => norm(o.text).includes(wanted));
                                if (!opt) continue;
                                sel.value = opt.value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                return true;
                            }
                            return false;
                        }""",
                        [attr_type],
                    )
                    if not ok:
                        return False, f"Attribute Type '{attr_type}' not set (option not found)"
                except Exception as e:
                    return False, f"Attribute Type set error: {e}"

            # 4) Editable checkbox
            should_check = _norm(editable) in ("true", "yes", "1")
            try:
                cb_loc = editor_frame.locator('input[type="checkbox"]')
                if cb_loc.count() > 0:
                    set_checkbox_state(cb_loc.first, should_check)
            except Exception:
                pass  # Editable is optional

            # 5) Click the 'Add' submit button (ICEfaces uses iceSubmit; JS click is most reliable)
            try:
                clicked = editor_frame.evaluate(
                    r"""() => {
                        const btn = document.querySelector('input[type="submit"][value="Add"]')
                                 || document.querySelector('input[type="submit"]');
                        if (!btn) return false;
                        // Trigger via onclick if present (ICEfaces iceSubmit pattern)
                        const oc = btn.getAttribute('onclick');
                        if (oc) {
                            try {
                                const form = btn.form || btn.closest('form');
                                const evt = new MouseEvent('click', {bubbles: true, cancelable: true});
                                btn.dispatchEvent(evt);
                                return true;
                            } catch (e) {}
                        }
                        btn.click();
                        return true;
                    }"""
                )
                if not clicked:
                    return False, "Add button not found in editor"
            except Exception as e:
                return False, f"Add button click error: {e}"

            # ICEfaces AJAX needs time to process the row and reset the form
            self.page.wait_for_timeout(1200)
            return True, "ok"

        # ---------------------------------------------------------------
        # Normalize and group rows by hierarchy
        # ---------------------------------------------------------------
        grouped: dict = {}
        current_hierarchy = ""
        skipped_missing_hierarchy = []
        for idx, row in enumerate(attributes_rows, start=1):
            if not isinstance(row, dict):
                continue
            attr_name = _get_row_val(row, ["attributename", "name"])
            hierarchy = _get_row_val(row, ["hierarchy", "hierarchyname"])
            if hierarchy:
                current_hierarchy = hierarchy
            effective_hierarchy = current_hierarchy.strip()

            if not attr_name:
                continue
            if not effective_hierarchy:
                skipped_missing_hierarchy.append({"row": idx, "attribute": attr_name})
                continue

            grouped.setdefault(effective_hierarchy, []).append(row)

        if not grouped:
            return "ERROR: No valid attribute rows found (need Attribute Name + Hierarchy)."

        list_frame = _wait_for_attributes_list()
        if list_frame is None:
            return "ERROR: Could not find Attributes list frame (Hierarchy Name/Actions table)."

        results = []
        for hierarchy_name, rows in grouped.items():
            # Open the editor for this hierarchy (pencil click)
            opened = _open_hierarchy_editor(list_frame, hierarchy_name)
            if not opened:
                results.append({
                    "hierarchy": hierarchy_name,
                    "status": "ERROR",
                    "reason": f"Could not find/click pencil icon for '{hierarchy_name}' in list",
                })
                continue

            # The same frame now shows the editor (content changed in place)
            self.page.wait_for_timeout(1_500)
            editor_frame = list_frame

            # Verify editor loaded
            editor_ready = False
            try:
                editor_ready = editor_frame.evaluate(
                    """() => !!document.querySelector('input[name$="attributeName"], input[id$="attributeName"]')"""
                )
            except Exception:
                pass
            if not editor_ready:
                results.append({
                    "hierarchy": hierarchy_name,
                    "status": "ERROR",
                    "reason": "Editor form did not load after pencil click (Attribute Name input not found)",
                })
                continue

            row_success = 0
            row_errors = []
            for row in rows:
                attr_name = _get_row_val(row, ["attributename", "name"])
                map_to = _get_row_val(row, ["mapto", "map", "mapsto"])
                attr_type = _get_row_val(row, ["attributetype", "type", "datatype"])
                editable = _get_row_val(row, ["editable", "iseditable"])

                ok, msg = _fill_attr_row(editor_frame, attr_name, map_to, attr_type, editable)
                if ok:
                    row_success += 1
                else:
                    row_errors.append(f"{attr_name}: {msg}")

            # Click Save to persist all added attributes
            try:
                save_loc = editor_frame.locator('input[type="submit"][value="Save"]')
                if save_loc.count() > 0:
                    save_loc.click(timeout=3_000)
                    self.page.wait_for_timeout(1_000)
            except Exception as e:
                row_errors.append(f"Save button error: {e}")

            status = "OK" if not row_errors else ("PARTIAL" if row_success > 0 else "ERROR")
            results.append({
                "hierarchy": hierarchy_name,
                "status": status,
                "configured": row_success,
                "total": len(rows),
                "errors": row_errors[:5],
            })

            # After Save the frame should return to the list view
            self.page.wait_for_timeout(500)
            list_frame = _find_list_frame() or list_frame

        if skipped_missing_hierarchy:
            return (
                f"Configured attributes by hierarchy: {results}; "
                f"Skipped rows with missing hierarchy before first hierarchy value: {skipped_missing_hierarchy[:5]}"
            )
        return f"Configured attributes by hierarchy: {results}"
