"""
Direct automation script for hierarchy form filling
This bypasses the LLM agent and directly fills the form using Playwright
"""
import time
from playwright.sync_api import sync_playwright
from excel_config import load_runtime_config_from_excel, load_hierarchy_configs_from_master_data

def automate_hierarchy_form():
    """Complete automation: login -> customer -> config -> menu -> hierarchy form -> fill -> save"""
    
    # Load Excel data
    print("Loading Excel configuration...")
    runtime = load_runtime_config_from_excel("Test Documentxl.xlsx", "Credentials", 1)
    configs = load_hierarchy_configs_from_master_data("Test Documentxl.xlsx", "Master data")
    
    if not configs:
        print("ERROR: No hierarchy configs found in Excel!")
        return False
    
    primary = configs[0]
    print(f"Hierarchy to create: {primary.hierarchy_name}")
    print(f"Levels: {primary.levels}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        try:
            # STEP 1: LOGIN
            print("\n[1] Logging in...")
            page.goto("http://dev3049.dev.e2open.com:9480/Main.action", wait_until="domcontentloaded")
            page.fill("#Main_userid", runtime.app_username)
            page.fill("#Main_password", runtime.app_password)
            page.click("#Main_submit")
            time.sleep(3)
            
            # STEP 2: SELECT CUSTOMER
            print("[2] Selecting customer: {}...".format(runtime.customer_name))
            page.wait_for_selector("iframe[name='bodyContent']", timeout=10000)
            time.sleep(1)
            
            # Find bodyContent frame
            body_frame = None
            for frame in page.frames:
                if frame.name == "bodyContent":
                    body_frame = frame
                    break
            
            if body_frame:
                body_frame.wait_for_selector("#customerDD", timeout=10000)
                body_frame.select_option("#customerDD", label=runtime.customer_name)
                time.sleep(2)
            
            # STEP 3: OPEN CONFIGURATION
            print("[3] Opening configuration {}...".format(runtime.configuration_number))
            time.sleep(1)
            # Find and click the read-only icon for the config
            page.wait_for_selector("td", timeout=10000)  # Table with configs
            time.sleep(1)
            
            # Try to find and click a link matching the config number or read-only icon
            config_row = page.query_selector(f"text='{runtime.configuration_number}'")
            if config_row:
                # Find parent tr and then the icon/link
                parent_tr = config_row.evaluate("el => el.closest('tr')")
                if parent_tr:
                    # Look for read-only or view icon
                    icon = parent_tr.query_selector("a, img")
                    if icon:
                        icon.click()
                        time.sleep(3)
            
            # STEP 4: NAVIGATE TO HIERARCHY
            print("[4] Navigating to Master data > Hierarchy...")
            page.wait_for_selector("text=Master data", timeout=10000)
            page.click("text=Master data")
            time.sleep(1)
            page.click("text=Hierarchy")
            time.sleep(3)
            
            # STEP 5: CLICK "ADD NEW"
            print("[5] Clicking 'Add New' button...")
            add_new = page.query_selector("text=Add New")
            if add_new:
                add_new.click()
                time.sleep(3)
            else:
                print("    WARNING: 'Add New' button not found. Trying alt methods...")
                # Try button
                buttons = page.query_selector_all("button")
                for btn in buttons:
                    if "add" in (btn.text_content() or "").lower():
                        btn.click()
                        time.sleep(3)
                        break
            
            # STEP 6: TAKE SCREENSHOT TO SEE FORM
            print("[6] Taking screenshot of form...")
            screenshot = page.screenshot()
            with open("form_screenshot.png", "wb") as f:
                f.write(screenshot)
            print("    Screenshot saved to form_screenshot.png")
            
            # STEP 7: GET ALL FRAMES TO FIND FORM
            print("[7] Checking all frames for form...")
            frames_info = []
            for i, f in enumerate(page.frames):
                try:
                    content = f.evaluate("() => document.body.innerText[:100]")
                    url_short = f.url[:60]
                    frames_info.append((i, url_short, content))
                    print(f"    Frame {i}: {url_short}")
                except:
                    pass
            
            # STEP 8: FIND AND READ FORM FIELDS
            print("[8] Finding form fields...")
            
            # Try different selector approaches
            hierarchy_name_field = None
            level_name_field = None
            add_level_button = None
            save_button = None
            
            # Approach 1: Direct selectors
            try:
                hierarchy_name_field = page.query_selector("#hierarchyForm\\:name, [name='hierarchyForm:name'], #hierarchyName, [name='hierarchyName'], input[placeholder*='Hierarchy'], input[placeholder*='Name']")
            except:
                pass
            
            # Approach 2: Search by label text
            if not hierarchy_name_field:
                inputs = page.query_selector_all("input[type='text']")
                print(f"    Found {len(inputs)} text inputs. Checking first few...")
                for inp in inputs[:5]:
                    try:
                        name = inp.get_attribute("name") or ""
                        id_attr = inp.get_attribute("id") or ""
                        placeholder = inp.get_attribute("placeholder") or ""
                        print(f"      - Input: name='{name}', id='{id_attr}', placeholder='{placeholder}'")
                        if "hierarchy" in name.lower() or "name" in name.lower():
                            hierarchy_name_field = inp
                    except:
                        pass
            
            # Find Add Level button
            buttons = page.query_selector_all("button")
            print(f"    Found {len(buttons)} buttons. Checking...")
            for btn in buttons[:10]:
                try:
                    text = (btn.text_content() or "").strip().lower()
                    print(f"      - Button: '{text}'")
                    if text and "add" in text and "level" in text:
                        add_level_button = btn
                    elif text == "add":
                        add_level_button = btn
                    if text == "save":
                        save_button = btn
                except:
                    pass
            
            # STEP 9: FILL HIERARCHY NAME
            print("[9] Filling hierarchy name: {}...".format(primary.hierarchy_name))
            if hierarchy_name_field:
                try:
                    hierarchy_name_field.fill(primary.hierarchy_name)
                    print("    ✓ Hierarchy name filled")
                except Exception as e:
                    print(f"    ERROR filling name: {e}")
            else:
                print("    ERROR: Could not find hierarchy name field!")
                # Try filling any text input
                inputs = page.query_selector_all("input[type='text']")
                if inputs:
                    inputs[0].fill(primary.hierarchy_name)
            
            time.sleep(1)
            
            # STEP 10: ADD LEVELS
            print("[10] Adding levels...")
            for i, level in enumerate(primary.levels):
                print(f"    Adding level {i+1}: {level}...")
                
                # Find level input field
                level_inputs = page.query_selector_all("input[type='text']")
                level_input = None
                for inp in level_inputs:
                    name = inp.get_attribute("name") or ""
                    if "level" in name.lower() and "name" not in name.lower().replace("levelname", ""):
                        level_input = inp
                        break
                
                if level_input:
                    try:
                        level_input.fill(level)
                        print(f"      ✓ Filled level input with '{level}'")
                    except Exception as e:
                        print(f"      ERROR: {e}")
                
                # Click Add button
                if add_level_button:
                    try:
                        add_level_button.click()
                        time.sleep(1)
                        print(f"      ✓ Clicked Add button")
                    except Exception as e:
                        print(f"      ERROR clicking add: {e}")
                else:
                    print(f"      WARNING: Add button not found for level {i+1}")
            
            # STEP 11: SAVE
            print("[11] Clicking Save button...")
            save_btn = page.query_selector("button:has-text('Save'), [type='submit'], button[name='save']")
            if not save_btn:
                save_btn = save_button
            
            if save_btn:
                try:
                    save_btn.click()
                    time.sleep(3)
                    print("    ✓ Save clicked")
                except Exception as e:
                    print(f"    ERROR clicking save: {e}")
            
            # STEP 12: VERIFY SUCCESS
            print("[12] Verifying success...")
            page_content = page.evaluate("() => document.body.innerText")
            if primary.hierarchy_name in page_content or "success" in page_content.lower():
                print("    ✓ SUCCESS! Hierarchy appears to have been created.")
            else:
                print("    Check browser window to verify hierarchy was created")
            
            print("\n✅ Automation complete. Browser window kept open for inspection.")
            print("Press Ctrl+C to close the browser, or inspect manually.")
            
            # Keep browser open
            while True:
                time.sleep(1)
            
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)
            browser.close()
            return False

if __name__ == "__main__":
    automate_hierarchy_form()
