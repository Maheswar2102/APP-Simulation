from playwright.sync_api import sync_playwright

from browser_tools import set_checkbox_state


HTML = """
<!DOCTYPE html>
<html>
<body>
  <input id="icefaces-checkbox" type="checkbox">
  <script>
    const checkbox = document.getElementById('icefaces-checkbox');

    // Simulate ICEfaces-like behavior: mouse click does not persist state,
    // keyboard Space on focus is the supported interaction.
    checkbox.addEventListener('click', (event) => {
      event.preventDefault();
      checkbox.checked = false;
    });

    checkbox.addEventListener('keydown', (event) => {
      if (event.code === 'Space' || event.key === ' ') {
        event.preventDefault();
        checkbox.checked = !checkbox.checked;
      }
    });
  </script>
</body>
</html>
"""


def test_checkbox_space_toggle() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(HTML)

        locator = page.locator("#icefaces-checkbox")

        locator.click()
        assert locator.is_checked() is False

        assert set_checkbox_state(locator, True) is True
        assert locator.is_checked() is True

        assert set_checkbox_state(locator, False) is True
        assert locator.is_checked() is False

        browser.close()


if __name__ == "__main__":
    test_checkbox_space_toggle()
    print("checkbox keyboard regression test passed")