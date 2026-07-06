"""
Playwright UI QA for Elcoria Healthcare PoC - Transcript Rendering check.

Investigates: backend logs "WS sent partial_transcript: ..." but user reports
nothing renders. Does the browser receive & display partial_transcript in
#transcriptPanel?

PASS criteria:
  (a) page contains any .transcript-partial or .transcript-final element
      with non-empty text, OR
  (b) a partial_transcript / final_transcript frame was received on the WS.

Server is assumed to be already running at http://127.0.0.1:8000/.
"""
import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

URL = "http://127.0.0.1:8000/"
HERE = Path(__file__).parent
SESSION_READY_TIMEOUT_S = 30
SPEAK_SECONDS = 6
POST_STOP_WAIT_S = 5


def _parse_ws_payload(payload):
    if not isinstance(payload, str):
        return None
    s = payload.strip()
    if not s or s[0] != "{":
        return None
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _truncate(s, n):
    if not isinstance(s, str):
        return s
    return s if len(s) <= n else s[:n] + f"...<+{len(s)-n}>"


def run_test(pw):
    result = {
        "console_log": [],
        "console_warn": [],
        "console_errors": [],
        "page_errors": [],
        "ws_frames_received": [],   # list of dicts {ts, payload}
        "ws_frames_sent": [],
        "ws_session_ready": False,
        "ws_partial_count": 0,
        "ws_final_count": 0,
        "ws_first_partial_payload": None,
        "ws_first_final_payload": None,
        "mic_button_text_before": None,
        "mic_button_text_after_start": None,
        "mic_button_text_after_stop": None,
        "mic_became_stop": False,
        "transcript_panel_text": None,
        "transcript_panel_html": None,
        "transcript_partial_elements": 0,
        "transcript_final_elements": 0,
        "transcript_partial_text_nonempty": False,
        "transcript_final_text_nonempty": False,
        "exception": None,
    }

    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            "--autoplay-policy=no-user-gesture-required",
        ],
    )
    try:
        context = browser.new_context(permissions=["microphone"])
        context.grant_permissions(["microphone"], origin="http://127.0.0.1:8000")
        page = context.new_page()

        def on_console(msg):
            try:
                loc = msg.location or {}
                entry = {
                    "text": msg.text,
                    "location": f"{loc.get('url','')}:{loc.get('lineNumber','')}",
                }
                if msg.type == "error":
                    result["console_errors"].append(entry)
                elif msg.type == "warning":
                    result["console_warn"].append(entry)
                elif msg.type == "log":
                    result["console_log"].append(entry)
            except Exception:
                pass

        def on_pageerror(exc):
            result["page_errors"].append(str(exc))

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        ws_state = {"session_ready_time": None}

        def on_ws(ws):
            def on_frame_received(payload):
                ts = round(time.time(), 3)
                if isinstance(payload, (bytes, bytearray)):
                    result["ws_frames_received"].append(
                        {"ts": ts, "payload": f"<binary {len(payload)} bytes>"}
                    )
                    return
                result["ws_frames_received"].append({"ts": ts, "payload": payload})
                obj = _parse_ws_payload(payload)
                if obj is None:
                    return
                t = obj.get("type")
                if t == "session_ready":
                    result["ws_session_ready"] = True
                    ws_state["session_ready_time"] = time.time()
                elif t == "partial_transcript":
                    result["ws_partial_count"] += 1
                    if result["ws_first_partial_payload"] is None:
                        result["ws_first_partial_payload"] = payload
                elif t == "final_transcript":
                    result["ws_final_count"] += 1
                    if result["ws_first_final_payload"] is None:
                        result["ws_first_final_payload"] = payload

            def on_frame_sent(payload):
                ts = round(time.time(), 3)
                if isinstance(payload, (bytes, bytearray)):
                    result["ws_frames_sent"].append(
                        {"ts": ts, "payload": f"<binary {len(payload)} bytes>"}
                    )
                else:
                    result["ws_frames_sent"].append({"ts": ts, "payload": payload})

            ws.on("framereceived", on_frame_received)
            ws.on("framesent", on_frame_sent)

        page.on("websocket", on_ws)

        # Navigate
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)

        # Wait up to 30s for session_ready
        deadline = time.time() + SESSION_READY_TIMEOUT_S
        while time.time() < deadline:
            if result["ws_session_ready"]:
                break
            page.wait_for_timeout(250)

        if not result["ws_session_ready"]:
            result["exception"] = (
                f"session_ready not received within {SESSION_READY_TIMEOUT_S}s"
            )
            # continue anyway — we still want to capture state

        # Mic button text before click
        try:
            result["mic_button_text_before"] = (
                page.eval_on_selector("#micBtn", "el => el.textContent.trim()")
            )
        except Exception:
            pass

        # Click mic to start
        try:
            page.click("#micBtn", timeout=5000)
        except Exception as e:
            result["exception"] = f"mic start click failed: {e}"

        # Small settle then capture button text
        page.wait_for_timeout(500)
        try:
            result["mic_button_text_after_start"] = (
                page.eval_on_selector("#micBtn", "el => el.textContent.trim()")
            )
        except Exception:
            pass

        btn_txt = (result["mic_button_text_after_start"] or "").lower()
        if "stop" in btn_txt:
            result["mic_became_stop"] = True

        # Speak via fake media for 6 seconds (minus the 500ms settle)
        page.wait_for_timeout(SPEAK_SECONDS * 1000 - 500)

        # Click mic to stop
        try:
            page.click("#micBtn", timeout=5000)
        except Exception as e:
            if not result["exception"]:
                result["exception"] = f"mic stop click failed: {e}"

        # Wait 5s for straggling frames
        page.wait_for_timeout(POST_STOP_WAIT_S * 1000)

        # Mic button text after stop
        try:
            result["mic_button_text_after_stop"] = (
                page.eval_on_selector("#micBtn", "el => el.textContent.trim()")
            )
        except Exception:
            pass

        # Read #transcriptPanel
        try:
            panel = page.evaluate(
                """() => {
                    const p = document.querySelector('#transcriptPanel');
                    if (!p) return null;
                    const partials = Array.from(p.querySelectorAll('.transcript-partial'));
                    const finals   = Array.from(p.querySelectorAll('.transcript-final'));
                    return {
                        text: (p.textContent || '').trim(),
                        html: p.innerHTML,
                        partialCount: partials.length,
                        finalCount: finals.length,
                        partialTexts: partials.map(e => (e.textContent || '').trim()),
                        finalTexts:   finals.map(e => (e.textContent || '').trim()),
                    };
                }"""
            )
            if panel:
                result["transcript_panel_text"] = panel["text"]
                result["transcript_panel_html"] = panel["html"]
                result["transcript_partial_elements"] = panel["partialCount"]
                result["transcript_final_elements"]   = panel["finalCount"]
                result["transcript_partial_text_nonempty"] = any(
                    t for t in panel["partialTexts"]
                )
                result["transcript_final_text_nonempty"] = any(
                    t for t in panel["finalTexts"]
                )
            else:
                result["transcript_panel_text"] = "<#transcriptPanel not found>"
        except Exception as e:
            result["transcript_panel_text"] = f"<panel read error: {e}>"

        # Screenshot for diagnostics
        try:
            page.screenshot(path=str(HERE / "test_ui_qa_final.png"), full_page=True)
        except Exception:
            pass

        context.close()
    except Exception as e:
        result["exception"] = f"{type(e).__name__}: {e}"
    finally:
        browser.close()
    return result


def compute_verdict(r):
    has_dom = (
        r["transcript_partial_text_nonempty"] or r["transcript_final_text_nonempty"]
    )
    has_ws = (r["ws_partial_count"] > 0) or (r["ws_final_count"] > 0)
    if has_dom or has_ws:
        return "PASS", has_dom, has_ws
    return "FAIL", has_dom, has_ws


def main():
    with sync_playwright() as pw:
        print(f"\n{'='*70}\nQA RUN - Transcript Rendering\n{'='*70}", flush=True)
        r = run_test(pw)

    verdict, has_dom, has_ws = compute_verdict(r)

    print("\n" + "#" * 70)
    print(f"# VERDICT: {verdict}")
    print(f"#   transcript DOM has non-empty .transcript-partial/.final: {has_dom}")
    print(f"#   WS partial/final frames received:                       {has_ws}")
    print("#" * 70)
    print(f"  session_ready received:        {r['ws_session_ready']}")
    print(f"  WS partial_transcript count:   {r['ws_partial_count']}")
    print(f"  WS final_transcript count:     {r['ws_final_count']}")
    print(f"  WS frames received total:      {len(r['ws_frames_received'])}")
    print(f"  WS frames sent total:          {len(r['ws_frames_sent'])}")
    print(f"  console.error count:           {len(r['console_errors'])}")
    print(f"  console.warn count:            {len(r['console_warn'])}")
    print(f"  page errors:                   {len(r['page_errors'])}")
    print(f"  mic text before:               {r['mic_button_text_before']!r}")
    print(f"  mic text after start:          {r['mic_button_text_after_start']!r}")
    print(f"  mic text after stop:           {r['mic_button_text_after_stop']!r}")
    print(f"  mic became 'Stop Recording':   {r['mic_became_stop']}")
    print(f"  .transcript-partial elements:  {r['transcript_partial_elements']}")
    print(f"  .transcript-final   elements:  {r['transcript_final_elements']}")
    if r["exception"]:
        print(f"  exception/note:                {r['exception']}")

    # WS frames received from server (truncated body 150 chars)
    print(f"\n  WS FRAMES RECEIVED FROM SERVER ({len(r['ws_frames_received'])}):")
    for i, f in enumerate(r["ws_frames_received"]):
        print(f"    [{i:3d}] t={f['ts']} {_truncate(f['payload'], 150)}")

    # console.error
    print(f"\n  CONSOLE.ERROR ({len(r['console_errors'])}):")
    for e in r["console_errors"]:
        print(f"    >>> {e['text']}  @ {e['location']}")

    # console.warn
    print(f"\n  CONSOLE.WARN ({len(r['console_warn'])}):")
    for e in r["console_warn"]:
        print(f"    >>> {e['text']}  @ {e['location']}")

    # page errors
    if r["page_errors"]:
        print(f"\n  PAGE ERRORS ({len(r['page_errors'])}):")
        for e in r["page_errors"]:
            print(f"    >>> {e}")

    # First partial / final payloads (full)
    if r["ws_first_partial_payload"]:
        print("\n  FIRST partial_transcript FRAME (full):")
        print(f"    >>> {r['ws_first_partial_payload']}")
    if r["ws_first_final_payload"]:
        print("\n  FIRST final_transcript FRAME (full):")
        print(f"    >>> {r['ws_first_final_payload']}")

    # #transcriptPanel innerHTML truncated to 800 chars
    html = r.get("transcript_panel_html") or ""
    print("\n  #transcriptPanel innerHTML (truncated to 800):")
    print(f"    {_truncate(html, 800) if html else '<empty or missing>'}")

    print(f"\n  #transcriptPanel textContent (truncated to 400):")
    print(f"    {_truncate(r.get('transcript_panel_text') or '', 400)}")

    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
