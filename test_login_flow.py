"""
Direct test of form interaction after login
"""
from playwright.sync_api import sync_playwright
import time
from excel_config import load_runtime_config_from_excel, load_hierarchy_configs_from_master_data

# Load config
runtime = load_runtime_config_from_excel("Test Documentxl.xlsx", "Credentials", 1)
configs = load_hierarchy_configs_from_master_data("Test Documentxl.xlsx", "Master data")

print(f"Loaded: username={runtime.app_username}, customer={runtime.customer_name}")
print(f"Hierarchy configs: {[(c.hierarchy_key, c.hierarchy_name, c.levels) for c in configs]}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    print("\n1. Navigating to app...")
    page.goto("http://dev3049.dev.e2open.com:9480/Main.action", wait_until="domcontentloaded")
    time.sleep(1)
    
    print("2. Logging in...")
    page.fill("#Main_userid", runtime.app_username)
    page.fill("#Main_password", runtime.app_password)
    page.click("#Main_submit")
    time.sleep(3)
    
    print("3. Checking frames and customer dropdown...")
    frames = page.frames
    print(f"   Frames: {len(frames)}")
    for i, f in enumerate(frames):
        print(f"   - Frame {i}: {f.url[:80]}")
    
    # Wait for bodyContent frame to load
    page.wait_for_selector("iframe[name='bodyContent']", timeout=10000)
    time.sleep(2)
    
    body_frame = page.frame_by_name("bodyContent")
    print(f"\n4. bodyContent frame loaded: {body_frame.url if body_frame else 'NOT FOUND'}")
    
    if body_frame:
        # Check if dropdowns exist
        print("5. Looking for customer dropdown...")
        try:
            options = body_frame.query_selector_all("#customerDD option")
            print(f"   Found {len(options)} options in #customerDD")
            for opt in options[:5]:
                print(f"   - {opt.text_content()}")
        except:
            print("   ERROR: Could not find #customerDD")
        
        print("\n6. Selecting customer: NISSAN...")
        try:
            body_frame.select_option("#customerDD", label="NISSAN")
            print("   Selected NISSAN")
            time.sleep(2)
        except Exception as e:
            print(f"   ERROR selecting: {e}")
    
    print("\n✅ Test complete. Check browser for current state.")
    page.pause()
    browser.close()
