/* Elcoria — main app (live backend wiring per INSTRUCTIONS.md §3-4) */

const { useState, useEffect, useRef, useCallback } = React;

const DEFAULT_BIO = { pitch_mean: 145, pitch_std: 16, jitter: 0.010, shimmer: 0.048, hnr: 19.0, energy: 0.10 };

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "showEnglish": true,
  "simulateDisconnect": false
}/*EDITMODE-END*/;

function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);

  // Connection state driven by the live WebSocket
  const [connection, setConnection] = useState("disconnected"); // "connected" | "disconnected"
  const [config, setConfig] = useState("lightweight-cpu");

  // Session state
  const [recording, setRecording] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [utterances, setUtterances] = useState([]);
  const [currentMood, setCurrentMood] = useState(null);
  const [bio, setBio] = useState(DEFAULT_BIO);
  const [bioHistory, setBioHistory] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [prediction, setPrediction] = useState(null);

  // Live infra refs (do not trigger re-render)
  const wsRef = useRef(null);
  const micRef = useRef(null);
  const startedAtRef = useRef(null);
  const rafRef = useRef(null);

  // ── Session reset ──────────────────────────────────────────────────────────
  const resetSession = useCallback(() => {
    setElapsedMs(0);
    setUtterances([]);
    setCurrentMood(null);
    setBio(DEFAULT_BIO);
    setBioHistory([]);
    setQuestions([]);
    setPrediction(null);
    startedAtRef.current = null;
  }, []);

  // ── WebSocket message handlers (the integration surface from §3.1) ─────────
  const handleSessionStart = useCallback((msg) => {
    setSessionId(msg.session_id);
  }, []);

  const handleTranscriptPartial = useCallback((msg) => {
    const tStart = (msg.ts_ms || 0) / 1000;
    setUtterances((prev) => {
      const without = prev.filter((u) => u.uid !== msg.uid);
      return [...without, {
        uid: msg.uid,
        kind: "partial",
        text: msg.text || "",
        tStart,
      }];
    });
  }, []);

  const handleTranscriptFinal = useCallback((msg) => {
    const tr = msg.transcript || {};
    const emo = msg.emotion || {};
    const bm = msg.biomarkers || DEFAULT_BIO;
    const tStart = (msg.ts_ms || 0) / 1000;

    setUtterances((prev) => {
      const without = prev.filter((u) => u.uid !== msg.uid);
      return [...without, {
        uid: msg.uid,
        kind: "final",
        text: tr.text || "",
        en: tr.en || "",
        tokens: tr.tokens || [{ t: tr.text || "" }],
        label: emo.label || "neutral",
        asrConfidence: tr.confidence ?? 0,
        bio: bm,
        tStart,
      }];
    });
    if (emo.scores) {
      setCurrentMood({
        scores: emo.scores,
        label: emo.label || "neutral",
        confidence: emo.confidence ?? 0,
      });
    }
    setBio(bm);
    setBioHistory((h) => [...h.slice(-23), bm]);
  }, []);

  const handleIntentUpdate = useCallback((msg) => {
    if (msg.prediction) {
      setPrediction({ ...msg.prediction, updatedAgo: "just now" });
    }
    if (Array.isArray(msg.questions) && msg.questions.length > 0) {
      setQuestions((prev) => {
        const existing = new Set(prev.map((q) => q.hu));
        const fresh = msg.questions.filter((q) => q && q.hu && !existing.has(q.hu));
        return [...fresh, ...prev];
      });
    }
  }, []);

  const handleError = useCallback((msg) => {
    console.error("[Elcoria] backend error:", msg);
    showToast(`Backend error: ${msg.message || msg.code || "unknown"}`);
  }, []);

  // ── Recording lifecycle ────────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    resetSession();
    setConnection("disconnected");

    const ws = new ElcoriaWebSocket({
      config,
      onOpen: () => {
        // Honor the simulate-disconnect tweak even when the socket is up.
        if (!tweaks.simulateDisconnect) setConnection("connected");
      },
      onClose: () => {
        setConnection("disconnected");
        // If the socket dropped while we were still recording, halt mic capture.
        if (micRef.current) {
          micRef.current.stop();
          micRef.current = null;
        }
        setRecording(false);
      },
      onSessionStart: handleSessionStart,
      onTranscriptPartial: handleTranscriptPartial,
      onTranscriptFinal: handleTranscriptFinal,
      onIntentUpdate: handleIntentUpdate,
      onError: handleError,
      onUnknown: (m) => console.log("[Elcoria] unhandled message:", m),
    });

    try {
      ws.connect();
      wsRef.current = ws;
    } catch (err) {
      console.error(err);
      showToast(`Could not open WebSocket: ${err.message}`);
      return;
    }

    // Start mic capture and stream PCM frames into the socket.
    const mic = new MicCapture({
      targetRate: 16000,
      frameMs: 250,
      onFrame: (frame) => wsRef.current && wsRef.current.sendAudio(frame),
    });

    try {
      await mic.start();
      micRef.current = mic;
      startedAtRef.current = performance.now();
      setRecording(true);
    } catch (err) {
      console.error("Mic capture failed:", err);
      showToast(`Microphone unavailable: ${err.message}`);
      ws.close();
      wsRef.current = null;
    }
  }, [config, tweaks.simulateDisconnect, resetSession, handleSessionStart, handleTranscriptPartial, handleTranscriptFinal, handleIntentUpdate, handleError]);

  const stopRecording = useCallback(() => {
    if (micRef.current) {
      micRef.current.stop();
      micRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setRecording(false);
  }, []);

  const handleRecordToggle = useCallback(() => {
    if (recording) stopRecording();
    else startRecording();
  }, [recording, startRecording, stopRecording]);

  // ── Upload audio (POST /upload/{session_id}, server replays as PCM) ────────
  const handleUpload = useCallback(async (file) => {
    // Behavior: open a session, post the file, then keep the socket open so
    // results stream back. The current backend exposes /upload/{session_id}
    // which decodes + paces the file through the orchestrator.
    resetSession();

    const ws = new ElcoriaWebSocket({
      config,
      onOpen: async () => {
        if (!tweaks.simulateDisconnect) setConnection("connected");
        startedAtRef.current = performance.now();
        setRecording(true);
        try {
          // Wait briefly for session.start so /upload finds the session.
          await new Promise((r) => setTimeout(r, 200));
          const sid = wsRef.current?.sessionId;
          if (!sid) throw new Error("No session id");
          const form = new FormData();
          form.append("file", file);
          const res = await fetch(`/upload/${encodeURIComponent(sid)}`, {
            method: "POST",
            body: form,
          });
          if (!res.ok) {
            const detail = await res.text();
            throw new Error(`Upload failed (${res.status}): ${detail}`);
          }
          showToast(`Uploaded ${file.name}`);
        } catch (err) {
          console.error(err);
          showToast(`Upload failed: ${err.message}`);
        }
      },
      onClose: () => {
        setConnection("disconnected");
        setRecording(false);
      },
      onSessionStart: handleSessionStart,
      onTranscriptPartial: handleTranscriptPartial,
      onTranscriptFinal: handleTranscriptFinal,
      onIntentUpdate: handleIntentUpdate,
      onError: handleError,
    });
    ws.connect();
    wsRef.current = ws;
  }, [config, tweaks.simulateDisconnect, resetSession, handleSessionStart, handleTranscriptPartial, handleTranscriptFinal, handleIntentUpdate, handleError]);

  // ── Elapsed timer ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!recording) return;
    const id = setInterval(() => {
      if (startedAtRef.current) {
        setElapsedMs(performance.now() - startedAtRef.current);
      }
    }, 100);
    return () => clearInterval(id);
  }, [recording]);

  // ── Keyboard shortcut: ⌘/Ctrl+R toggles recording ──────────────────────────
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "r") {
        e.preventDefault();
        handleRecordToggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleRecordToggle]);

  // ── "updated Ns ago" ticker ────────────────────────────────────────────────
  useEffect(() => {
    if (!prediction) return;
    const startedAt = performance.now();
    const id = setInterval(() => {
      const secs = Math.round((performance.now() - startedAt) / 1000);
      setPrediction((p) => p ? { ...p, updatedAgo: secs < 2 ? "just now" : `${secs}s ago` } : p);
    }, 1000);
    return () => clearInterval(id);
  }, [prediction?.name]);

  // ── Simulate-disconnect tweak — flips the LED even while the socket is open
  useEffect(() => {
    if (!wsRef.current) return;
    setConnection(tweaks.simulateDisconnect ? "disconnected" : "connected");
  }, [tweaks.simulateDisconnect]);

  // ── Tear down on unmount ───────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (micRef.current) micRef.current.stop();
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  return (
    <div className="app">
      <TopBar
        recording={recording}
        onRecordToggle={handleRecordToggle}
        onUpload={handleUpload}
        config={config}
        onConfigChange={setConfig}
        connection={connection}
        session={sessionId ? `session ${sessionId.slice(0, 8)}` : "no session"}
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
        resetSession={resetSession}
        recording={recording}
        stopRecording={stopRecording}
        startRecording={startRecording}
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

/* ---- Tweaks panel — kept slim for live mode ---- */
function ElcoriaTweaks({ tweaks, setTweak, resetSession, recording, stopRecording, startRecording }) {
  return (
    <TweaksPanel title="Tweaks">
      <TweakSection label="Display">
        <TweakToggle
          label="Show English gloss"
          value={tweaks.showEnglish}
          onChange={(v) => setTweak("showEnglish", v)}
        />
      </TweakSection>

      <TweakSection label="Session">
        <TweakButton
          label={recording ? "Stop & reset" : "Reset session"}
          onClick={() => { if (recording) stopRecording(); resetSession(); }}
        />
      </TweakSection>

      <TweakSection label="Debug">
        <TweakToggle
          label="Simulate disconnect"
          value={tweaks.simulateDisconnect}
          onChange={(v) => setTweak("simulateDisconnect", v)}
        />
      </TweakSection>
    </TweaksPanel>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
