# Elcoria — UI Handoff Package

High-fidelity, interactive frontend for the streaming ASR + emotion + intent analysis console. Drop this into the FastAPI/Kubernetes project and wire it to the live WebSocket pipeline.

---

## 1. What you're holding

| File | Purpose |
|---|---|
| `index.html` | Entry point. Loads React 18 + Babel standalone (in-browser JSX) and all component scripts. |
| `styles.css` | Full design system: clinical light palette, Geist + Geist Mono + Instrument Serif type, panel chrome, animations, responsive grid. |
| `app.jsx` | Root component. Holds session state, simulation loop, keyboard shortcuts, toasts, tweaks panel wiring. **This is where you replace the simulator with a real WebSocket client.** |
| `topbar.jsx` | Top bar — brand mark, record/stop button, upload audio, config dropdown, connection LED. |
| `transcript-panel.jsx` | Live transcript with mood ribbon, per-utterance emotion chips, biomarker strip, waveform. Newest utterance at the top. |
| `questions-panel.jsx` | Recommended clinical questions. Latest suggestion is a glowing hero card; earlier ones collapse beneath, click to expand. |
| `condition-panel.jsx` | Predicted condition. Urgency meter → current assessment hero → differential → escalate button. |
| `icons.jsx` | Hand-drawn outline icon set (1.6px stroke, 16×16). |
| `scenarios.js` | **Demo data only.** Pre-recorded Hungarian healthcare call timeline used to drive the UI without a backend. Delete or stub once the real WebSocket is wired in. |
| `tweaks-panel.jsx` | Helper for the in-page tweaks panel (playback speed, English gloss toggle, simulate disconnect). Safe to keep or remove. |

The whole thing is **zero-build** — no bundler, no npm. Open `index.html` in a browser and it works.

---

## 2. Running the prototype locally

```bash
cd elcoria-ui
python -m http.server 8000
# or any static server
open http://localhost:8000
```

You should see a populated end-state on load. Click **Start recording** to reset and replay the simulated call in real time (~22 s). The recording button auto-stops at the end. **⌘R** (or **Ctrl+R**) toggles recording. Toggle the toolbar **Tweaks** to expose the in-page tweaks panel.

---

## 3. Integration plan (mapping to the build spec)

The UI is structured to match the pipeline stages from the build spec — there is a 1:1 mapping between every backend signal and a UI region.

### 3.1 Where each backend signal lands

```
backend stage             →  UI consumer in app.jsx
─────────────────────────────────────────────────────────
faster-whisper            →  setUtterances([…]) (transcript-panel)
                              kind: "partial" → grey, animated caret
                              kind: "final"   → full text + tokens
wav2vec2 SER              →  setCurrentMood({ scores, label, confidence })
openSMILE / parselmouth   →  setBio({ pitch_mean, pitch_std, jitter,
                                       shimmer, hnr, energy })
                              setBioHistory([…last 24 windows…])
Qwen/Claude fusion        →  setQuestions([…]) (recommended questions)
                              setPrediction({…})  (condition panel)
VAD utterance boundary    →  triggers final-utterance unlock animation
                              (already wired — fires on `kind: "final"`)
```

### 3.2 What to delete / replace

**Delete from `app.jsx`:**

- The `useEffect` that pre-populates the session from `SCENARIO` (search for `didInitRef`)
- The simulation `setInterval` tick loop (search for `SCENARIO.steps`)
- The biomarker noise `setInterval` (the small jitter loop)
- The keyboard handler can stay or be removed — your call

**Delete entirely:**

- `scenarios.js` and its `<script src="scenarios.js">` tag in `index.html`

**Add:**

- A WebSocket client (see §4) that calls the same setters: `setUtterances`, `setCurrentMood`, `setBio`, `setBioHistory`, `setQuestions`, `setPrediction`, `setElapsedMs`, `setConnection`.

The setters are the integration surface — nothing else needs to change. Component props don't change.

---

## 4. WebSocket message contract

The UI expects one of four message types over the WebSocket, all JSON. This matches the output schema from §11 of the build spec, with one envelope-level addition (`type`) so the client can dispatch.

### 4.1 Connection lifecycle

```javascript
// client → server (on Start recording click)
ws = new WebSocket("wss://elcoria.local/v1/stream?session_id=…&config=lightweight-cpu");

// server → client first message
{ "type": "session.start", "session_id": "…", "ts_ms": 0 }
```

While the socket is open, set `connection = "connected"`. On close/error, set `"disconnected"` — the LED + label react automatically.

### 4.2 Partial transcript

Emitted every ~300 ms while a single utterance is being recognized.

```json
{
  "type": "transcript.partial",
  "uid": "u17",
  "ts_ms": 12340,
  "text": "Fáj a mellkasom…"
}
```

UI: appends/replaces a partial utterance with that `uid`. A blinking caret renders automatically.

### 4.3 Final utterance + mood + biomarkers (fan-out result)

Emitted on VAD silence > 500 ms — i.e. the orchestrator has joined all three parallel stages for one utterance.

```json
{
  "type": "transcript.final",
  "uid": "u17",
  "ts_ms": 13800,
  "transcript": {
    "text": "Fáj a mellkasom és néha nehezen kapok levegőt.",
    "en": "My chest hurts and sometimes I have trouble breathing.",
    "language": "hu",
    "confidence": 0.88,
    "tokens": [
      { "t": "Fáj a " },
      { "t": "mellkasom", "tag": "symptom", "title": "Chest pain" },
      { "t": " és néha " },
      { "t": "nehezen kapok levegőt", "tag": "symptom", "title": "Dyspnea" },
      { "t": "." }
    ]
  },
  "emotion": {
    "label": "anxious",
    "confidence": 0.88,
    "scores": {
      "neutral": 0.18, "anxious": 0.62, "fearful": 0.10,
      "sad": 0.08, "angry": 0.00, "happy": 0.02
    }
  },
  "biomarkers": {
    "pitch_mean": 178.4,
    "pitch_std": 34.7,
    "jitter": 0.018,
    "shimmer": 0.074,
    "hnr": 14.1,
    "energy": 0.17
  }
}
```

UI side:

```js
setUtterances(prev => {
  const without = prev.filter(u => u.uid !== msg.uid);
  return [...without, {
    uid: msg.uid,
    kind: "final",
    text: msg.transcript.text,
    en: msg.transcript.en,
    tokens: msg.transcript.tokens,
    label: msg.emotion.label,
    asrConfidence: msg.transcript.confidence,
    bio: msg.biomarkers,
    tStart: msg.ts_ms / 1000,
  }];
});
setCurrentMood({
  scores: msg.emotion.scores,
  label: msg.emotion.label,
  confidence: msg.emotion.confidence,
});
setBio(msg.biomarkers);
setBioHistory(h => [...h.slice(-23), msg.biomarkers]);
```

**Token tagging convention** — the transcript panel underlines tokens with one of three CSS classes by `tag`:

| `tag` value | Visual treatment | Use for |
|---|---|---|
| `symptom` | green underline + green wash | clinically named symptoms |
| `risk` | amber underline + amber wash | risk factors, history, distress markers |
| `crisis` | red underline + red wash | emergency requests, crisis language |

If the backend doesn't tag tokens, send `tokens: [{ t: "<full text>" }]` and the UI renders the text plainly. Tagging is a server-side decision — the NER or rule engine that runs after Whisper should attach these.

### 4.4 Intent / condition update (fusion stage output)

Emitted whenever the fusion LLM produces a new assessment — typically on each final utterance, but can be debounced.

```json
{
  "type": "intent.update",
  "ts_ms": 13900,
  "prediction": {
    "name": "Possible cardiopulmonary discomfort",
    "icd": "R07.4 + R06.0",
    "level": 3,
    "level_label": "Urgent",
    "confidence": 0.62,
    "reasoning": "Chest pain + intermittent dyspnea. Vocal jitter and shimmer trending upward…",
    "differential": [
      { "name": "Stable angina",  "icd": "I20.8", "pct": 0.34 },
      { "name": "Panic attack",   "icd": "F41.0", "pct": 0.21 },
      { "name": "GERD",           "icd": "K21.0", "pct": 0.13 }
    ]
  },
  "questions": [
    { "p": "high", "hu": "Kisugárzik-e a fájdalom…", "en": "Does the pain radiate…", "tags": ["cardiac"] },
    { "p": "med",  "hu": "Mennyi ideje tartanak a tünetek?",  "en": "How long…",      "tags": ["onset"] }
  ]
}
```

UI side:

```js
setPrediction({ ...msg.prediction, updatedAgo: "just now" });

// Prepend new questions, dedupe by .hu
setQuestions(prev => {
  const existing = new Set(prev.map(q => q.hu));
  const fresh = msg.questions.filter(q => !existing.has(q.hu));
  return [...fresh, ...prev];
});
```

**Field constraints:**

- `level` is an integer 1–4. The urgency meter and accent color use this directly.
   - 1 = Routine (accent green)
   - 2 = Concerned (accent green)
   - 3 = Urgent (amber)
   - 4 = Crisis (red — also unlocks the dispatch button)
- `confidence` is 0–1.
- `p` (question priority) is one of `"high"`, `"med"`, `"low"`.

### 4.5 Errors

```json
{ "type": "error", "code": "asr.timeout", "message": "…" }
```

The current UI does not surface errors visibly — adding a toast in `app.jsx`'s `Toaster` is a 3-line change. The `showToast(msg)` helper is already wired.

---

## 5. Where to make changes

### 5.1 Brand / accent color

In `styles.css`, top of file:

```css
--accent: #00B07A;
--accent-strong: #00936A;
```

Change both. Everything green-tinted derives from these via `oklch`-style overlays, so swap them and the whole UI follows.

### 5.2 Adding a new config option to the dropdown

In `topbar.jsx`, `ConfigSelect` component, extend the `options` array:

```js
const options = [
  { id: "lightweight-cpu", label: "Lightweight CPU", meta: "Default", icon: <IconCpu /> },
  { id: "gpu-fp16",        label: "GPU FP16",        meta: "Beta",    icon: <IconCpu /> },
];
```

Pass the selected `id` back to the server when opening the WebSocket.

### 5.3 Adding more mood categories

In `scenarios.js` and the message schema, the six tracked moods are `neutral / anxious / fearful / sad / angry / happy`. To add more, edit:

1. `transcript-panel.jsx` → `MoodRibbon` → the `order` array
2. `styles.css` → `.tag-mood[data-mood="…"] .dot` rules and `.mood-bar > span[data-k="…"]` rules

### 5.4 Hungarian/English UI strings

All static UI strings (panel titles, eyebrows, buttons) are in English. The patient transcript is Hungarian. To localize the UI shell, search for these strings and replace:

```
"Live transcript", "Recommended questions", "Predicted condition",
"Start recording", "Stop recording", "Upload audio",
"Lightweight CPU", "Connected", "Disconnected",
"Current assessment", "Differential",
"Dispatch emergency services", "Escalation not required",
"Suggested next question", "Earlier suggestions"
```

---

## 6. Production checklist

Before deploying:

- [ ] Replace `scripts type="text/babel"` with a precompiled bundle. Babel-in-the-browser is fine for a PoC but adds ~200 ms to first paint and warns in the console. Use Vite (`npm create vite@latest -- --template react`) and copy the JSX in.
- [ ] Pin the React UMD URLs (already done — see the `integrity=` hashes in `index.html`).
- [ ] Replace `scenarios.js` with the real WebSocket client.
- [ ] Wire the **Upload audio** button — `topbar.jsx` already passes the `File` object up via `onUpload(file)`. Send it via REST `POST /v1/upload` or stream it through the WebSocket as PCM frames.
- [ ] Audit the LLM call: per the build spec §13, mask PII before any external API call. The UI never sees raw audio — only labels, scores, and text — so PII masking is the backend's job.
- [ ] Add CSP headers — the inline styles are minimal; the only external origin is Google Fonts.
- [ ] Decide whether to inline the Google Fonts (Geist, Geist Mono, Instrument Serif) for on-prem deploys without egress.

---

## 7. Visual / interaction contract

These are the design choices the UI bakes in. If the backend can't honor them, the UI degrades gracefully but loses signal.

- **Newest-first in transcript and questions.** The top of each list is always the most recent item. The latest utterance gets a green accent rail; older ones dim to muted text.
- **Mood ribbon shows the full 6-class vector**, not just the argmax. If the SER head emits only an argmax, you'll get a single-color ribbon — fine but less informative.
- **Biomarker history is 24 windows.** The sparkline assumes a sliding window with ~50 % overlap on 1.5–3 s frames — i.e. roughly the last 30–60 seconds. Adjust the slice in `app.jsx` (`h.slice(-23)`) if your window cadence differs.
- **Escalation button is gated on `level === 4`.** This is deliberate — keep this as the only path to dispatch from the UI, so the gate matches the backend's crisis threshold.
- **`updated Ns ago` ticks every second on the condition panel.** It resets on every `intent.update` whose `prediction.name` differs. If you stream `intent.update` every utterance with the same name, the timer will still reset — fine for "live" feel.

---

## 8. Known limitations / open work

- No diarization UI yet. The transcript labels every line "Patient" — if you turn on pyannote, add a `speaker` field on `transcript.final` and render it where `<span className="speaker">Patient</span>` lives.
- No barge-in support. The UI assumes one-direction streaming (caller → operator). For Pipecat/LiveKit-style bidirectional voice agents, the top bar needs a TTS-out toggle.
- No audit log export. NIS2 (build spec §13) requires audit logging — handled server-side, but you may want a "Download session report" button in the top bar.
- Tweaks panel includes a "Show English gloss" toggle that defaults to on. For production with clinical users, default it off.

---

That's the full handoff. The component tree is shallow on purpose — three panels, each self-contained — so adding signals (new biomarkers, new intent labels, diarization, etc.) is local work, not a refactor.
