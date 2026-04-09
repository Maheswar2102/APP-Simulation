"""
Test script to directly test the form filling logic
"""
import time
from playwright.sync_api import sync_playwright

def test_form_interaction():
    """Test clicking Add New and filling the form"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Navigate to hierarchy
        url = "http://dev3049.dev.e2open.com:9480/hierarchy.action"
        print(f"Navigating to {url}...")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Wait for page to load
        time.sleep(2)
        
        # Get all frames
        frames = page.frames
        print(f"\nTotal frames: {len(frames)}")
        for i, frame in enumerate(frames):
            print(f"  Frame {i}: {frame.url}")
        
        # Look for Add New button on main page
        print("\n--- Main Page Content ---")
        content = page.evaluate("() => document.body.innerText")
        print(content[:500])
        
        # Try to find and click Add New button
        print("\nSearching for 'Add New' button...")
        try:
            # Try different selectors
            buttons = page.query_selector_all("button, input[type='button'], [role='button']")
            print(f"Found {len(buttons)} button elements")
            for btn in buttons[:5]:
                text = btn.text_content()
                print(f"  - Button text: {text}")
                if text and "Add New" in text or "add" in text.lower():
                    print(f"  -> FOUND potential match: {text}")
                    print(f"     Clicking it...")
                    btn.click()
                    time.sleep(3)
                    break
        except Exception as e:
            print(f"Error searching buttons: {e}")
        
        # After clicking, check what appears
        print("\n--- After clicking Add New ---")
        frames_after = page.frames
        print(f"Frames after: {len(frames_after)}")
        for i, frame in enumerate(frames_after):
            print(f"  Frame {i}: {frame.url}")
            try:
                content = frame.evaluate("() => document.body.innerText")
                if "Hierarchy" in content or "hierarchy" in content:
                    print(f"    -> FORM DETECTED in frame {i}")
                    print(f"    Content preview: {content[:300]}")
            except:
                pass
        
        # Check for form fields
        print("\n--- Form Fields ---")
        all_inputs = page.query_selector_all("input, textarea, select")
        print(f"Found {len(all_inputs)} input elements:")
        for inp in all_inputs[:10]:
            name = inp.get_attribute("name") or ""
            id_attr = inp.get_attribute("id") or ""
            type_attr = inp.get_attribute("type") or ""
            value = inp.input_value() if hasattr(inp, 'input_value') else ""
            print(f"  - Type: {type_attr}, Name: {name}, ID: {id_attr}, Value: {value[:30]}")
        
        print("\n✅ Test complete. Check browser window for form.")
        page.pause()  # Pause to let user inspect
        
        browser.close()

if __name__ == "__main__":
    test_form_interaction()
