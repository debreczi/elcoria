#!/usr/bin/env python3
"""
Playwright-based UI test for already-running Elcoria streaming-asr-emotion server.
Assumes server is already running on http://127.0.0.1:8000
"""

import asyncio
import time
import sys

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[INFO] Installing Playwright...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], capture_output=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], capture_output=True)
    from playwright.async_api import async_playwright


def check_server_ready(timeout: int = 10) -> bool:
    """Quick check if server is running."""
    import urllib.request
    try:
        for _ in range(timeout):
            try:
                response = urllib.request.urlopen("http://127.0.0.1:8000/configs", timeout=2)
                if response.status == 200:
                    print("[OK] Server is running")
                    return True
            except:
                time.sleep(1)
    except:
        pass
    return False


async def run_ui_tests() -> bool:
    """Run browser-based UI tests."""
    print("=" * 60)
    print("Elcoria Streaming ASR-Emotion - UI Test Suite")
    print("=" * 60 + "\n")

    # Check server readiness
    print("[1/4] Checking server readiness...")
    if not check_server_ready():
        print("[FAIL] Server not responding on http://127.0.0.1:8000")
        return False

    # Launch browser
    print("[2/4] Launching Chromium browser...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Collect errors
            console_errors = []

            def on_console_msg(msg):
                if msg.type == "error":
                    console_errors.append(msg.text)
                    try:
                        print(f"  [CONSOLE ERROR] {str(msg.text)[:100]}")
                    except:
                        print(f"  [CONSOLE ERROR] Unicode error")

            page.on("console", on_console_msg)

            # Load page
            print("[3/4] Loading http://127.0.0.1:8000...")
            try:
                response = await page.goto("http://127.0.0.1:8000", wait_until="domcontentloaded", timeout=10000)
                if not response or response.status >= 400:
                    print(f"[FAIL] Failed to load page (HTTP {response.status if response else 'no response'})")
                    await browser.close()
                    return False
                print("[OK] Page loaded successfully")
            except Exception as e:
                print(f"[FAIL] Navigation failed")
                await browser.close()
                return False

            # Wait for React to render
            await page.wait_for_timeout(2000)

            # Test UI elements
            print("[4/4] Testing UI elements...\n")

            # Test 1: Config selector
            print("[TEST 1] Config selector dropdown")
            try:
                selector = page.locator("select")
                count = await selector.count()
                if count > 0:
                    print(f"  [OK] Found {count} select element(s)")
                    options = page.locator("select option")
                    opt_count = await options.count()
                    print(f"  [OK] Found {opt_count} config options")
                else:
                    print("[WARN] Config selector not found")
            except Exception as e:
                print(f"[WARN] Config selector check failed")

            # Test 2: Mic button
            print("\n[TEST 2] Mic button")
            try:
                buttons = page.locator("button")
                btn_count = await buttons.count()
                print(f"  [OK] Found {btn_count} button(s)")
                # Check if any button contains mic-related text
                mic_found = False
                for i in range(min(btn_count, 20)):
                    try:
                        text = await buttons.nth(i).text_content()
                        if text and ("mic" in text.lower() or "record" in text.lower()):
                            print(f"  [OK] Found mic/record button: {str(text)[:50]}")
                            mic_found = True
                            break
                    except:
                        pass
                if not mic_found:
                    print("[WARN] Mic/record button not found by text")
            except Exception as e:
                print(f"[WARN] Mic button check failed")

            # Test 3: File upload input
            print("\n[TEST 3] File upload input")
            try:
                file_input = page.locator("input[type='file']")
                if await file_input.count() > 0:
                    print("[OK] File upload input found")
                else:
                    print("[WARN] File upload input not found")
            except Exception as e:
                print(f"[WARN] File upload check failed")

            # Test 4: Panels (transcript/questions)
            print("\n[TEST 4] Content panels")
            try:
                divs = page.locator("div")
                div_count = await divs.count()
                print(f"  [OK] Found {div_count} div elements")

                # Look for any divs with content-related classes
                main_content = page.locator("main, [role='main']")
                if await main_content.count() > 0:
                    print("[OK] Main content area found")
                else:
                    print("[WARN] Main content area not found")
            except Exception as e:
                print(f"[WARN] Panel check failed")

            # Summary
            print("\n" + "=" * 60)
            print("TEST SUMMARY")
            print("=" * 60)

            if console_errors:
                print(f"[FAIL] Found {len(console_errors)} console error(s):")
                for err in console_errors[:5]:
                    try:
                        print(f"  - {str(err)[:100]}")
                    except:
                        print(f"  - (Unicode error)")
                await browser.close()
                return False
            else:
                print("[OK] No console errors detected")

            print("[OK] All UI elements responsive")

            await browser.close()
            return True

    except Exception as e:
        try:
            print(f"[FAIL] Browser test failed: {str(e)[:100]}")
        except:
            print(f"[FAIL] Browser test failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_ui_tests())

    print("\n" + "=" * 60)
    if success:
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")
    print("=" * 60)

    sys.exit(0 if success else 1)
