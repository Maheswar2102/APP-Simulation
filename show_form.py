"""
Simple test to show the form structure
"""
import time
from playwright.sync_api import sync_playwright
from excel_config import load_runtime_config_from_excel, load_hierarchy_configs_from_master_data

# Load config
runtime = load_runtime_config_from_excel("Test Documentxl.xlsx", "Credentials", 1)
configs = load_hierarchy_configs_from_master_data("Test Documentxl.xlsx", "Master data")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    print("1. Logging in...")
    page.goto("http://dev3049.dev.e2open.com:9480/Main.action", wait_until="domcontentloaded")
    page.fill("#Main_userid", runtime.app_username)
    page.fill("#Main_password", runtime.app_password)
    page.click("#Main_submit")
    time.sleep(5)
    
    print("2. Finding customer dropdown...")
    for frame in page.frames:
        if frame.name == "bodyContent":
            frame.select_option("#customerDD", label="NISSAN")
            time.sleep(2)
            break
    
    print("3. Clicking configuration read-only...")
    # Wait for config to open
    for frame in page.frames:
        try:
            items = frame.query_selector_all("[onclick]")
            for item in items:
                onclick = item.get_attribute("onclick") or ""
                if "6771" in onclick or "view" in onclick.lower():
                    item.click()
                    time.sleep(2)
                    break
        except:
            pass
    
    print("4. Opening menu: Master data > Hierarchy...")
    try:
        page.click("text=Master data")
        time.sleep(1)
    except:
        pass
    
    try:
        page.click("text=Hierarchy")
        time.sleep(3)
    except:
        pass
    
    print("5. Before clicking Add New")
    page.screenshot(path="before_add_new.png")
    
    print("6. Clicking Add New...")
    try:
        page.click("text=Add New")
        time.sleep(4)
    except as e:
        print(f"Click failed: {e}")
    
    print("7. Form should appear now")
    page.screenshot(path="form_visible.png")
    
    print("8. All form fields:")
    fields = page.query_selector_all("input, textarea, select, button")
    for i, field in enumerate(fields[:15]):
        tag = field.tag_name
        name = field.get_attribute("name") or ""
        id_attr = field.get_attribute("id") or ""
        type_attr = field.get_attribute("type") or ""
        value = field.get_attribute("value") or ""
        text = (field.text_content() or "")[:50]
        print(f"  {i}. <{tag}> name='{name}' id='{id_attr}' type='{type_attr}' value='{value}' text='{text}'")
    
    print("\n✅ Screenshots saved: before_add_new.png, form_visible.png")
    input("Press Enter to close browser...")
    browser.close()
