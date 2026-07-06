/* Transcript panel — live ASR output with mood + biomarkers */

const { useEffect, useRef, useMemo } = React;

function MoodRibbon({ scores, label, confidence, hasData }) {
  // scores: { neutral, anxious, sad, fearful, angry, happy }
  const order = ["neutral", "anxious", "fearful", "sad", "angry", "happy"];
  const total = order.reduce((s, k) => s + (scores?.[k] || 0), 0) || 1;

  return (
    <div className="mood-ribbon" aria-label="Current patient mood vector">
      <div className="label">Mood</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div className="mood-bar">
          {order.map((k) => (
            <span
              key={k}
              data-k={k}
              style={{ width: `${((scores?.[k] || 0) / total) * 100}%` }}
            ></span>
          ))}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="tag tag-mood" data-mood={label || "neutral"} style={{ background: "transparent", border: "none", padding: 0 }}>
            <span className="dot"></span>
            <span>{hasData ? label : "awaiting signal"}</span>
          </span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-faint)", letterSpacing: "0.04em" }}>
            {hasData ? `conf ${(confidence * 100).toFixed(0)}%` : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}

function Tokens({ tokens, fallbackText }) {
  if (!tokens || tokens.length === 0) {
    return <>{fallbackText}</>;
  }
  return (
    <>
      {tokens.map((tok, i) => (
        tok.tag
          ? (
            <span key={i} className={`lex-token tag-${tok.tag}`} title={tok.title}>
              {tok.t}
            </span>
          )
          : <span key={i}>{tok.t}</span>
      ))}
    </>
  );
}

function Utterance({ u, showEnglish, latest }) {
  const ts = formatTs(u.tStart || 0);
  return (
    <div className={`utterance ${u.kind === "partial" ? "partial" : ""} ${latest ? "is-latest" : ""}`}>
      <div className="ts">
        {ts}
        <span className="speaker">Patient</span>
      </div>
      <div className="body">
        <div className="text">
          <Tokens tokens={u.tokens} fallbackText={u.text} />
        </div>
        {u.kind === "final" && showEnglish && u.en && (
          <div style={{ marginTop: 4, fontSize: 13, color: "var(--text-faint)", fontStyle: "italic", letterSpacing: 0 }}>
            “{u.en}”
          </div>
        )}
        {u.kind === "final" && (
          <div className="utt-meta">
            <span className="tag tag-mood" data-mood={u.label}>
              <span className="dot"></span>
              <span>{u.label}</span>
            </span>
            <span className="tag tag-conf">
              <span>asr {(u.asrConfidence * 100).toFixed(0)}%</span>
            </span>
            <span className="tag tag-conf">
              <span>pitch {u.bio.pitch_mean.toFixed(0)} Hz</span>
            </span>
            <span className="tag tag-conf">
              <span>hnr {u.bio.hnr.toFixed(1)} dB</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function formatTs(seconds) {
  const m = Math.floor(seconds / 60).toString().padStart(2, "0");
  const s = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function Waveform({ live }) {
  // 60 bars; if live, varying heights, otherwise idle (small)
  const bars = useMemo(() => {
    return Array.from({ length: 64 }, () => Math.random());
  }, []);
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    let raf;
    const animate = () => {
      if (!ref.current) return;
      const spans = ref.current.querySelectorAll("span");
      spans.forEach((sp, i) => {
        if (live) {
          // perlin-ish: combine two sines + noise
          const t = performance.now() / 240;
          const v = Math.abs(
            0.5 * Math.sin(t + i * 0.35) +
            0.35 * Math.sin(t * 1.7 + i * 0.6) +
            (Math.random() - 0.5) * 0.25
          );
          sp.style.height = `${Math.max(8, v * 100)}%`;
        } else {
          sp.style.height = `${4 + (i % 7) * 1.5}%`;
        }
      });
      raf = requestAnimationFrame(animate);
    };
    raf = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf);
  }, [live]);

  return (
    <div className={`waveform ${live ? "is-live" : ""}`} ref={ref}>
      {bars.map((_, i) => <span key={i} style={{ height: "10%" }}></span>)}
    </div>
  );
}

function BiomarkerStrip({ bio, history }) {
  const cells = [
    { k: "Pitch (μ)", v: bio.pitch_mean.toFixed(0), unit: "Hz", hKey: "pitch_mean" },
    { k: "Pitch (σ)", v: bio.pitch_std.toFixed(1), unit: "Hz", hKey: "pitch_std" },
    { k: "Jitter",    v: (bio.jitter * 100).toFixed(2), unit: "%", hKey: "jitter" },
    { k: "Shimmer",   v: (bio.shimmer * 100).toFixed(2), unit: "%", hKey: "shimmer" },
    { k: "HNR",       v: bio.hnr.toFixed(1), unit: "dB", hKey: "hnr" },
    { k: "Energy",    v: bio.energy.toFixed(2), unit: "rms", hKey: "energy" },
  ];

  return (
    <div className="bio-strip">
      {cells.map((c) => {
        const series = history.map((h) => h[c.hKey]);
        const min = Math.min(...series);
        const max = Math.max(...series);
        const range = max - min || 1;
        return (
          <div key={c.k} className="bio-cell">
            <div className="k">{c.k}</div>
            <div className="v">{c.v}<span className="unit">{c.unit}</span></div>
            <div className="spark">
              {series.map((s, i) => (
                <span
                  key={i}
                  style={{ height: `${20 + ((s - min) / range) * 80}%` }}
                ></span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TranscriptEmpty({ recording }) {
  return (
    <div className="t-empty">
      <div className="ring">
        <IconMic size={28} />
      </div>
      <h3>{recording ? "Listening…" : "Awaiting audio input"}</h3>
      <p>
        Press <span style={{ fontFamily: "var(--font-mono)", color: "var(--text)" }}>Start recording</span> to begin live transcription, or upload an audio file for offline analysis.
      </p>
      <div className="hint">
        <span className="kbd">⌘</span>
        <span className="kbd">R</span>
        <span>to toggle recording</span>
      </div>
    </div>
  );
}

function TranscriptPanel({ utterances, currentMood, bio, bioHistory, recording, sessionElapsedMs, showEnglish }) {
  const hasData = utterances.length > 0;
  const scrollRef = useRef(null);

  // Reversed: newest at top
  const reversed = [...utterances].reverse();

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }, [utterances.length]);

  return (
    <section className="panel" aria-label="Live transcript">
      <header className="panel-head">
        <div className="panel-title">
          <h2>Live transcript</h2>
        </div>
        <div className="right-meta">
          <span className="live-pill" data-on={recording}>
            <span className="ld"></span>
            {recording ? "Live" : "Idle"}
          </span>
          <span>HU · whisper-large-v3-hu</span>
        </div>
      </header>

      <div className="panel-body" ref={scrollRef}>
        {hasData ? (
          <>
            <MoodRibbon
              scores={currentMood?.scores || {}}
              label={currentMood?.label}
              confidence={currentMood?.confidence || 0}
              hasData={!!currentMood}
            />
            <div className="transcript">
              {reversed.map((u, i) => <Utterance key={u.uid} u={u} showEnglish={showEnglish} latest={i === 0} />)}
            </div>
          </>
        ) : (
          <TranscriptEmpty recording={recording} />
        )}
      </div>

      <footer className="panel-foot" style={{ flexDirection: "column", alignItems: "stretch", gap: 12, paddingTop: 12, paddingBottom: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr auto", alignItems: "center", gap: 12 }}>
          <Waveform live={recording} />
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)", letterSpacing: "0.08em" }}>
            {formatTs(sessionElapsedMs / 1000)} · 16 kHz · int8_float16
          </div>
        </div>
        <BiomarkerStrip bio={bio} history={bioHistory.length > 0 ? bioHistory : [bio]} />
      </footer>
    </section>
  );
}

window.TranscriptPanel = TranscriptPanel;
