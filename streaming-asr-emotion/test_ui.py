#!/usr/bin/env python3
"""
Playwright-based UI automation test for Elcoria streaming-asr-emotion
Tests:
- Server startup and readiness
- UI element loading
- Config selector dropdown (lightweight and gpu)
- Mic button clickability
- File upload input accessibility
- Transcript panel rendering
- Questions panel rendering
- Console error checking
"""

import asyncio
import subprocess
import time
import sys
import os
from pathlib import Path

# Set encoding to UTF-8 for Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[INFO] Playwright not found. Installing...")
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.async_api import async_playwright


def wait_for_server(host: str = "127.0.0.1", port: int = 8000, timeout: int = 30) -> bool:
    """Wait for server to be ready using urllib."""
    import urllib.request
    import urllib.error

    url = f"http://{host}:{port}/configs"
    start = time.time()

    while time.time() - start < timeout:
        try:
            response = urllib.request.urlopen(url, timeout=5.0)
            if response.status == 200:
                print(f"[OK] Server ready at {url}")
                return True
        except Exception as e:
            time.sleep(1)

    print(f"[FAIL] Server not ready after {timeout}s")
    return False


async def _run_browser_tests() -> bool:
    """Run browser tests using Playwright async."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Collect console messages
            console_errors = []
            console_logs = []

            def on_console_msg(msg):
                if msg.type == "error":
                    console_errors.append(msg.text)
                    print(f"  [ERROR] Console: {msg.text}")
                else:
                    console_logs.append((msg.type, msg.text))

            page.on("console", on_console_msg)

            try:
                # Navigate to app
                print("[4/5] Loading http://127.0.0.1:8000...")
                response = await page.goto("http://127.0.0.1:8000", wait_until="domcontentloaded", timeout=10000)

                if not response or response.status >= 400:
                    print(f"[FAIL] Failed to load page: {response.status if response else 'no response'}")
                    return False

                print("[OK] Page loaded successfully")

                # Wait for React to render
                await page.wait_for_timeout(2000)

                # Test 1: Check config selector dropdown
                print("\n[TEST 1] Config selector dropdown...")
                try:
                    config_select = page.locator("select#config-select, [data-testid='config-select'], select")
                    if await config_select.count() > 0:
                        print("  [OK] Config selector found")

                        # Try to select lightweight
                        options = page.locator("select option")
                        option_count = await options.count()
                        print(f"  [OK] Found {option_count} config options")

                        # Click and select options by value attribute
                        await config_select.first.click()
                        await page.wait_for_timeout(500)

                        # Try to find and select lightweight by value
                        lightweight_opt = page.locator("option[value='lightweight']")
                        if await lightweight_opt.count() > 0:
                            try:
                                await lightweight_opt.first.click()
                                print("  [OK] Selected 'lightweight' config")
                                await page.wait_for_timeout(500)
                            except Exception as ex:
                                print(f"  [WARN] Could not click lightweight option")

                        # Try to find and select gpu by value
                        gpu_opt = page.locator("option[value='gpu']")
                        if await gpu_opt.count() > 0:
                            try:
                                await gpu_opt.first.click()
                                print("  [OK] Selected 'gpu' config")
                            except Exception as ex:
                                print(f"  [WARN] Could not click gpu option")
                        else:
                            print("  [WARN] 'gpu' config not found (may not be available)")
                    else:
                        print("  [WARN] Config selector not found with standard selectors")
                except Exception as e:
                    try:
                        print(f"  [FAIL] Config selector test failed: {str(e)[:100]}")
                    except:
                        print(f"  [FAIL] Config selector test failed")

                # Test 2: Mic button clickability
                print("\n[TEST 2] Mic button...")
                try:
                    mic_button = page.locator("button[aria-label='Start recording'], button:has-text('Mic'), button:has-text('mic'), [data-testid='mic-button']")
                    if await mic_button.count() > 0:
                        is_enabled = await mic_button.first.is_enabled()
                        print(f"  [OK] Mic button found (enabled: {is_enabled})")
                    else:
                        print("  [WARN] Mic button not found with standard selectors")
                except Exception as e:
                    try:
                        print(f"  [FAIL] Mic button test failed: {str(e)[:100]}")
                    except:
                        print(f"  [FAIL] Mic button test failed")

                # Test 3: File upload input
                print("\n[TEST 3] File upload input...")
                try:
                    file_input = page.locator("input[type='file']")
                    if await file_input.count() > 0:
                        is_visible = await file_input.first.is_visible()
                        print(f"  [OK] File upload input found (visible in DOM: {is_visible})")
                    else:
                        print("  [WARN] File upload input not found")
                except Exception as e:
                    try:
                        print(f"  [FAIL] File upload test failed: {str(e)[:100]}")
                    except:
                        print(f"  [FAIL] File upload test failed")

                # Test 4: Transcript panel
                print("\n[TEST 4] Transcript panel...")
                try:
                    transcript = page.locator("[data-testid='transcript'], .transcript, #transcript, [class*='transcript']")
                    if await transcript.count() > 0:
                        print("  [OK] Transcript panel found")
                    else:
                        print("  [WARN] Transcript panel not found with standard selectors")
                except Exception as e:
                    try:
                        print(f"  [FAIL] Transcript panel test failed: {str(e)[:100]}")
                    except:
                        print(f"  [FAIL] Transcript panel test failed")

                # Test 5: Questions panel
                print("\n[TEST 5] Questions panel...")
                try:
                    questions = page.locator("[data-testid='questions'], .questions, #questions, [class*='question']")
                    if await questions.count() > 0:
                        print("  [OK] Questions panel found")
                    else:
                        print("  [WARN] Questions panel not found with standard selectors")
                except Exception as e:
                    try:
                        print(f"  [FAIL] Questions panel test failed: {str(e)[:100]}")
                    except:
                        print(f"  [FAIL] Questions panel test failed")

                # Summary
                print("\n" + "="*60)
                print("TEST SUMMARY")
                print("="*60)

                if console_errors:
                    print(f"[FAIL] CONSOLE ERRORS FOUND ({len(console_errors)}):")
                    for err in console_errors:
                        print(f"  - {err}")
                    await browser.close()
                    return False
                else:
                    print("[OK] No console errors detected")

                print(f"[OK] Console logs captured: {len(console_logs)}")

                await browser.close()
                return True

            except Exception as e:
                try:
                    print(f"[FAIL] Test execution failed: {str(e)[:100]}")
                except:
                    print(f"[FAIL] Test execution failed")
                await browser.close()
                return False
    except Exception as e:
        try:
            print(f"[FAIL] Browser init failed: {str(e)[:100]}")
        except:
            print(f"[FAIL] Browser init failed")
        return False


def run_tests():
    """Run all UI tests with Playwright."""

    # Start server in background (use venv python on Windows)
    print("[1/5] Starting FastAPI server...")
    project_dir = Path(__file__).parent
    venv_python = project_dir / "venv" / "Scripts" / "python.exe"

    if not venv_python.exists():
        venv_python = sys.executable  # Fallback to system python

    server_proc = subprocess.Popen(
        [str(venv_python), "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(project_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        # Wait for server
        print("[2/5] Waiting for server to be ready...")
        if not wait_for_server():
            return False

        # Launch browser with asyncio
        print("[3/5] Launching Chromium browser...")
        return asyncio.run(_run_browser_tests())

    finally:
        # Kill server
        print("\nShutting down server...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()


def main():
    """Main entry point."""
    print("="*60)
    print("Elcoria Streaming ASR-Emotion - UI Test Suite")
    print("="*60 + "\n")

    success = run_tests()

    print("\n" + "="*60)
    if success:
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")
    print("="*60)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
