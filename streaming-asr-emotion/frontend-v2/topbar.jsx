/* Elcoria Top Bar */

const { useState, useRef, useEffect } = React;

function ConfigSelect({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const options = [
    { id: "lightweight-cpu", label: "Lightweight CPU", meta: "Default", icon: <IconCpu /> },
  ];
  const current = options.find((o) => o.id === value) || options[0];

  return (
    <div className="select" ref={ref}>
      <button
        className="select-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="swatch"></span>
        {current.label}
      </button>
      {open && (
        <div className="select-menu" role="listbox">
          {options.map((o) => (
            <div
              key={o.id}
              className="select-item"
              role="option"
              aria-selected={o.id === value}
              onClick={() => { onChange(o.id); setOpen(false); }}
            >
              {o.icon}
              <span>{o.label}</span>
              <span className="meta">{o.meta}</span>
              {o.id === value && <IconCheck size={12} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConnectionLight({ state }) {
  return (
    <div className="conn" data-state={state}>
      <span className="led"></span>
      <span>{state === "connected" ? "Connected" : "Disconnected"}</span>
    </div>
  );
}

function ThemeToggle({ theme, onToggle }) {
  return (
    <button
      className="theme-toggle"
      onClick={onToggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
    >
      {theme === "dark" ? <IconSun /> : <IconMoon />}
    </button>
  );
}

function TopBar({
  recording, onRecordToggle,
  onUpload,
  config, onConfigChange,
  connection,
  session,
}) {
  const fileRef = useRef(null);

  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 8h2l1.4-3.5L8 13l1.6-5L11 8h3" />
          </svg>
        </div>
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1 }}>
          <span className="brand-name">Elcoria</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 9.5, letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--text-faint)", marginTop: 3 }}>
            Vocal Intelligence Console
          </span>
        </div>
        <span className="brand-sub">v0.4 · PoC</span>
        <span className="session-chip">
          <span className="dot" style={{ background: recording ? "var(--accent)" : undefined, boxShadow: recording ? "0 0 8px var(--accent)" : undefined }}></span>
          {session}
        </span>
      </div>

      <div className="cluster">
        <button
          className="btn-record"
          data-recording={recording}
          onClick={onRecordToggle}
          aria-pressed={recording}
        >
          <span className="rec-dot"></span>
          {recording ? "Stop recording" : "Start recording"}
        </button>

        <input
          ref={fileRef}
          type="file"
          accept="audio/*,.wav,.mp3,.m4a,.flac,.ogg"
          className="hidden-file"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onUpload(f);
            e.target.value = "";
          }}
        />
        <button className="btn" onClick={() => fileRef.current?.click()}>
          <IconUpload />
          Upload audio
        </button>

        <div className="divider-v"></div>

        <ConfigSelect value={config} onChange={onConfigChange} />
      </div>

      <div className="right">
        <ConnectionLight state={connection} />
      </div>
    </header>
  );
}

window.TopBar = TopBar;
