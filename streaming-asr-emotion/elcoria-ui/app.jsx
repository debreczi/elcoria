/* Elcoria — main app */

const { useState, useEffect, useRef, useCallback } = React;

const DEFAULT_BIO = { pitch_mean: 145, pitch_std: 16, jitter: 0.010, shimmer: 0.048, hnr: 19.0, energy: 0.10 };

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "speed": 1.0,
  "showEnglish": true
}/*EDITMODE-END*/;

function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);

  // Connection state — simulated
  const [connection, setConnection] = useState("connected"); // "connected" | "disconnected"
  const [config, setConfig] = useState("lightweight-cpu");

  // Recording / streaming state
  const [recording, setRecording] = useState(false);
  const [stepIdx, setStepIdx] = useState(-1); // last fully-fired step
  const [elapsedMs, setElapsedMs] = useState(0);
  const [utterances, setUtterances] = useState([]); // [{uid, kind, text, tokens, label, asrConfidence, bio, tStart}]
  const [currentMood, setCurrentMood] = useState(null);
  const [bio, setBio] = useState(DEFAULT_BIO);
  const [bioHistory, setBioHistory] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [prediction, setPrediction] = useState(null);

  const startedAtRef = useRef(null);
  const rafRef = useRef(null);
  const lastFiredRef = useRef(-1);

  const SCENARIO = window.SCENARIO;

  // Pre-populate with end-state on first mount so the UI is meaningful
  // before the user clicks anything. "Start recording" resets and replays.
  const didInitRef = useRef(false);
  useEffect(() => {
    if (didInitRef.current) return;
    didInitRef.current = true;
    const finals = SCENARIO.steps.filter((s) => s.kind === "final");
    setUtterances(finals.map((s) => ({
      uid: s.uid,
      kind: "final",
      text: s.text,
      en: s.en,
      tokens: s.tokens,
      label: s.label,
      asrConfidence: s.confidence,
      bio: s.bio,
      tStart: s.t,
    })));
    const last = finals[finals.length - 1];
    setCurrentMood({ scores: last.mood, label: last.label, confidence: last.confidence });
    setBio(last.bio);
    setBioHistory(finals.map((f) => f.bio));
    setQuestions([...SCENARIO.questions].reverse());
    const lastPred = SCENARIO.predictions[SCENARIO.predictions.length - 1];
    setPrediction({ ...lastPred, updatedAgo: "just now" });
    setElapsedMs(SCENARIO.steps[SCENARIO.steps.length - 1].t * 1000);
  }, []);

  // Reset all state to a fresh session
  const resetSession = useCallback(() => {
    setStepIdx(-1);
    setElapsedMs(0);
    setUtterances([]);
    setCurrentMood(null);
    setBio(DEFAULT_BIO);
    setBioHistory([]);
    setQuestions([]);
    setPrediction(null);
    startedAtRef.current = null;
    lastFiredRef.current = -1;
  }, []);

  // Main simulation loop
  useEffect(() => {
    if (!recording) return;

    if (!startedAtRef.current) startedAtRef.current = performance.now();
    const speed = tweaks.speed || 1.0;

    const tick = () => {
      const now = performance.now();
      const elapsedScenarioMs = (now - startedAtRef.current) * speed;
      setElapsedMs(elapsedScenarioMs);

      // Fire any scenario steps whose t has been reached
      const steps = SCENARIO.steps;
      for (let i = lastFiredRef.current + 1; i < steps.length; i++) {
        const s = steps[i];
        if (elapsedScenarioMs / 1000 >= s.t) {
          fireStep(s, i);
          lastFiredRef.current = i;
          setStepIdx(i);
        } else {
          break;
        }
      }

      // End of scenario — auto-stop
      const lastT = steps[steps.length - 1].t;
      if (elapsedScenarioMs / 1000 > lastT + 4) {
        setRecording(false);
      }
    };

    const id = setInterval(tick, 60);
    return () => clearInterval(id);
  }, [recording, tweaks.speed]);

  // Smoothly interpolate biomarkers between final utterances (gives a "live" feel)
  useEffect(() => {
    if (!recording) return;
    const id = setInterval(() => {
      setBio((b) => {
        // small noise around current values
        return {
          pitch_mean: b.pitch_mean + (Math.random() - 0.5) * 1.2,
          pitch_std:  Math.max(8, b.pitch_std + (Math.random() - 0.5) * 0.6),
          jitter:     Math.max(0.003, b.jitter + (Math.random() - 0.5) * 0.0005),
          shimmer:    Math.max(0.02,  b.shimmer + (Math.random() - 0.5) * 0.001),
          hnr:        Math.max(5,     b.hnr + (Math.random() - 0.5) * 0.2),
          energy:     Math.max(0.02,  b.energy + (Math.random() - 0.5) * 0.005),
        };
      });
    }, 350);
    return () => clearInterval(id);
  }, [recording]);

  function fireStep(s, i) {
    if (s.kind === "partial") {
      setUtterances((prev) => {
        // Replace any existing partial for same uid; otherwise append
        const filtered = prev.filter((u) => u.uid !== s.uid);
        return [...filtered, {
          uid: s.uid,
          kind: "partial",
          text: s.text,
          tStart: s.t,
        }];
      });
    } else if (s.kind === "final") {
      setUtterances((prev) => {
        const filtered = prev.filter((u) => u.uid !== s.uid);
        return [...filtered, {
          uid: s.uid,
          kind: "final",
          text: s.text,
          en: s.en,
          tokens: s.tokens,
          label: s.label,
          asrConfidence: s.confidence,
          bio: s.bio,
          tStart: s.t,
        }];
      });
      setCurrentMood({ scores: s.mood, label: s.label, confidence: s.confidence });
      setBio(s.bio);
      setBioHistory((h) => [...h.slice(-23), s.bio]);

      // Unlock questions/predictions tied to this step
      const stepNumber = utteranceNumberFromUid(s.uid);
      const matchedQs = SCENARIO.questions.filter((q) => q.after === stepNumber);
      if (matchedQs.length > 0) {
        setQuestions((qs) => {
          const existing = new Set(qs.map((q) => q.hu));
          const fresh = matchedQs.filter((q) => !existing.has(q.hu));
          return [...fresh, ...qs];
        });
      }
      const pred = SCENARIO.predictions.find((p) => p.after === stepNumber);
      if (pred) {
        setPrediction({ ...pred, updatedAgo: "just now" });
      }
    }
  }

  function utteranceNumberFromUid(uid) {
    // uid like "u1" -> 1
    return parseInt(uid.replace(/^u/, ""), 10);
  }

  const handleRecordToggle = () => {
    if (recording) {
      setRecording(false);
    } else {
      resetSession();
      setRecording(true);
    }
  };

  const handleUpload = (file) => {
    // For demo: same scenario plays. Show a small feedback in the session chip via console.
    resetSession();
    // small toast
    showToast(`Loaded ${file.name} — playing back at ${(tweaks.speed || 1).toFixed(1)}× speed`);
    setRecording(true);
  };

  // Keyboard shortcut
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "r") {
        e.preventDefault();
        handleRecordToggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [recording, tweaks.speed]);

  // "updated ago" tick for prediction
  useEffect(() => {
    if (!prediction) return;
    const startedAt = performance.now();
    const id = setInterval(() => {
      const secs = Math.round((performance.now() - startedAt) / 1000);
      setPrediction((p) => p ? { ...p, updatedAgo: secs < 2 ? "just now" : `${secs}s ago` } : p);
    }, 1000);
    return () => clearInterval(id);
  }, [prediction?.name]);

  return (
    <div className="app">
      <TopBar
        recording={recording}
        onRecordToggle={handleRecordToggle}
        onUpload={handleUpload}
        config={config}
        onConfigChange={setConfig}
        connection={connection}
        session={SCENARIO.session}
      />
      <main className="panels">
        <TranscriptPanel
          utterances={utterances}
          currentMood={currentMood}
          bio={bio}
          bioHistory={bioHistory}
          recording={recording}
          sessionElapsedMs={elapsedMs}
          showEnglish={tweaks.showEnglish}
        />
        <QuestionsPanel questions={questions} />
        <ConditionPanel prediction={prediction} />
      </main>

      <Toaster />

      <ElcoriaTweaks
        tweaks={tweaks}
        setTweak={setTweak}
        connection={connection}
        setConnection={setConnection}
        resetSession={resetSession}
        recording={recording}
        setRecording={setRecording}
      />
    </div>
  );
}

/* ---- tiny toast system ---- */
let toastRef = { add: () => {} };
function showToast(msg) { toastRef.add(msg); }

function Toaster() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    toastRef.add = (msg) => {
      const id = Math.random().toString(36).slice(2);
      setItems((i) => [...i, { id, msg }]);
      setTimeout(() => setItems((i) => i.filter((t) => t.id !== id)), 3200);
    };
  }, []);
  return (
    <div style={{ position: "fixed", bottom: 20, left: 20, display: "flex", flexDirection: "column", gap: 8, zIndex: 200 }}>
      {items.map((t) => (
        <div key={t.id} style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          padding: "10px 14px",
          borderRadius: "var(--r-md)",
          fontSize: 13,
          color: "var(--text)",
          boxShadow: "var(--shadow-md)",
          animation: "rise 0.3s var(--ease-out)",
        }}>{t.msg}</div>
      ))}
    </div>
  );
}

/* ---- Tweaks panel ---- */
function ElcoriaTweaks({ tweaks, setTweak, connection, setConnection, resetSession, recording, setRecording }) {
  return (
    <TweaksPanel title="Tweaks">
      <TweakSection label="Simulation">
        <TweakSlider
          label="Playback speed"
          value={tweaks.speed}
          min={0.5} max={4} step={0.25}
          unit="×"
          onChange={(v) => setTweak("speed", v)}
        />
        <TweakToggle
          label="Show English gloss"
          value={tweaks.showEnglish}
          onChange={(v) => setTweak("showEnglish", v)}
        />
        <TweakButton
          label={recording ? "Reset & restart" : "Restart session"}
          onClick={() => { setRecording(false); setTimeout(() => { resetSession(); setRecording(true); }, 50); }}
        />
      </TweakSection>

      <TweakSection label="Connection">
        <TweakRadio
          label="Backend state"
          value={connection}
          options={["connected", "disconnected"]}
          onChange={setConnection}
        />
      </TweakSection>
    </TweaksPanel>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
