# Elcoria — frontend-v2

Live-wired version of the `elcoria-ui` handoff package. The simulator and
`scenarios.js` are gone; in their place is a WebSocket client and a mic-capture
module that follow the v1 message contract from
`../elcoria-ui/INSTRUCTIONS.md §4`.

This directory is intentionally separate from `frontend/` so the previous PoC
UI can keep running while backend and models evolve in parallel.

## Files

| File | Purpose |
|---|---|
| `index.html` | Entry point. Loads React 18 + Babel standalone and the live scripts below. |
| `styles.css` | Design system (copied verbatim from `elcoria-ui`). |
| `icons.jsx`, `topbar.jsx`, `transcript-panel.jsx`, `questions-panel.jsx`, `condition-panel.jsx`, `tweaks-panel.jsx` | Panels (copied verbatim from `elcoria-ui`). |
| `mic-capture.js` | `getUserMedia` → 16 kHz mono Float32 PCM frames (250 ms by default). |
| `websocket-client.js` | `ElcoriaWebSocket` class implementing the v1 contract dispatch. |
| `app.jsx` | Root React app — replaces the simulator with the live WS + mic. |

## Running

The FastAPI backend in [`src/main.py`](../src/main.py) now serves this directory
at `/` and speaks the v1 contract on `/v1/stream`, so the full PoC runs from a
single port:

```bash
cd streaming-asr-emotion
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
# then open http://localhost:8000
```

For a UI-only preview (no backend), you can still serve the directory as static
files:

```bash
python -m http.server 8000 --directory frontend-v2
```

To point the UI at a non-default backend without editing code:

```
http://localhost:8000/?ws=ws://otherhost:9000/v1/stream
```

The `?ws=…` override is read by `websocket-client.js`.

## WebSocket contract assumed by the UI

Per `INSTRUCTIONS.md §4`, the UI expects the server to speak this contract:

- Connect URL: `ws(s)://…/v1/stream?session_id=<uuid>&config=<config-name>`
- Server → client JSON message types:
  - `session.start` — `{ type, session_id, ts_ms }`
  - `transcript.partial` — `{ type, uid, ts_ms, text }`
  - `transcript.final` — `{ type, uid, ts_ms, transcript, emotion, biomarkers }`
  - `intent.update` — `{ type, ts_ms, prediction, questions }`
  - `error` — `{ type, code, message }`
- Client → server:
  - Binary frames: raw Float32 LE PCM, 16 kHz, mono, ~250 ms each.
  - JSON: `{ type: "session.end" }` (optional) when the user stops recording.

**Backend status.** [`src/main.py`](../src/main.py) now implements the v1
contract on `/v1/stream` and the [`PipelineOrchestrator`](../src/orchestrator.py)
emits `transcript.partial` / `transcript.final` (bundled with `emotion` and
`biomarkers`) and `intent.update` directly. The legacy `/ws/{session_id}`
endpoint has been removed; the old `frontend/` UI no longer talks to this
backend.

Biomarkers (`pitch_mean`, `pitch_std`, `jitter`, `shimmer`, `hnr`, `energy`)
are computed from the utterance audio via parselmouth (Praat). If parselmouth
is unavailable, the orchestrator falls back to defaults plus a measured
`energy`. Intent prediction is currently a heuristic based on emotion + keyword
matching; questions come from the existing fusion stage, parsed line-by-line
into the `{p, hu, en, tags}` shape.

## Tweaks panel

Stripped down to what is meaningful in live mode:

- **Show English gloss** — toggles the English line under each utterance.
- **Reset session** — clears panels (and stops recording if it is running).
- **Simulate disconnect** — flips the LED to disconnected without actually
  closing the socket. Useful for screenshotting the disconnected state.

The playback-speed and scenario controls are gone — there is no simulator to
drive.

## What was removed vs. `elcoria-ui`

- `scenarios.js` — deleted (the live backend is the data source).
- The `useEffect` that pre-populated state from `SCENARIO` — deleted.
- The simulation `setInterval` tick loop — deleted.
- The biomarker noise `setInterval` — deleted; biomarkers update only on
  `transcript.final` now.

## Production checklist

Same as `../elcoria-ui/INSTRUCTIONS.md §6`. The big one before deploying is
swapping Babel-in-the-browser for a precompiled Vite bundle.
