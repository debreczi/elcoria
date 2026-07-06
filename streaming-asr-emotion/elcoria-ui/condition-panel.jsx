/* Predicted Condition panel */

function ConditionEmpty() {
  return (
    <div className="c-empty">
      <div className="pulser">
        <IconPulse size={20} />
      </div>
      <div className="msg">No prediction yet</div>
      <div className="sub">
        Condition inference begins after the first complete utterance with clinical signal.
      </div>
    </div>
  );
}

function UrgencyMeter({ level }) {
  return (
    <div className="urg-meter" data-level={level}>
      {[1, 2, 3, 4].map((n) => (
        <span key={n} className={n <= level ? "on" : ""}></span>
      ))}
    </div>
  );
}

function ConditionPanel({ prediction }) {
  if (!prediction) {
    return (
      <section className="panel" aria-label="Predicted condition">
        <header className="panel-head">
          <div className="panel-title">
            <h2>Predicted condition</h2>
          </div>
          <div className="right-meta">
            <span>—</span>
          </div>
        </header>
        <div className="panel-body">
          <ConditionEmpty />
        </div>
        <footer className="panel-foot">
          <IconShield size={12} />
          <span>Decision support · not a diagnosis</span>
        </footer>
      </section>
    );
  }

  const isCrisis = prediction.level >= 4;

  return (
    <section className="panel" aria-label="Predicted condition">
      <header className="panel-head">
        <div className="panel-title">
          <h2>Predicted condition</h2>
        </div>
        <div className="right-meta">
          <span>
            updated {prediction.updatedAgo || "just now"}
          </span>
        </div>
      </header>

      <div className="panel-body">
        <div className="cond-card">
          {/* 1. Urgency — at top */}
          <div className="cond-urgency" data-level={prediction.level}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="urg-label">Urgency</span>
              <span className="urg-val">
                {prediction.level_label} · Level {prediction.level}/4
              </span>
            </div>
            <UrgencyMeter level={prediction.level} />
          </div>

          {/* 2. Current assessment in text */}
          <div className="cond-assessment" data-level={prediction.level}>
            <div className="cond-eyebrow">
              <IconBrain size={11} />
              <span>Current assessment</span>
            </div>
            <h3 className="cond-name">{prediction.name}</h3>
            <div className="cond-icd">ICD-10 · {prediction.icd}</div>
            {prediction.reasoning && (
              <p className="cond-reasoning-text">{prediction.reasoning}</p>
            )}
            <div className="cond-confidence">
              <span className="cconf-label">Model confidence</span>
              <div className="cbar">
                <span style={{ width: `${prediction.confidence * 100}%` }}></span>
              </div>
              <div className="cval">{(prediction.confidence * 100).toFixed(0)}%</div>
            </div>
          </div>

          {prediction.differential && prediction.differential.length > 0 && (
            <div>
              <h4 className="section-h">Differential</h4>
              <div className="differential">
                {prediction.differential.map((d) => (
                  <div key={d.name} className="diff-row">
                    <div className="diff-name">
                      {d.name}
                      <span className="icd">{d.icd}</span>
                    </div>
                    <div className="diff-bar">
                      <span style={{ width: `${d.pct * 100}%` }}></span>
                    </div>
                    <div className="diff-pct">{(d.pct * 100).toFixed(0)}%</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <button
            className="escalate-btn"
            data-disabled={!isCrisis}
            disabled={!isCrisis}
            onClick={() => {
              if (isCrisis) alert("Mentő riasztva — ALS dispatched. (demo)");
            }}
          >
            <IconAmbulance size={14} />
            {isCrisis ? "Dispatch emergency services" : "Escalation not required"}
          </button>
        </div>
      </div>

      <footer className="panel-foot">
        <IconShield size={12} />
        <span>Decision support · not a diagnosis</span>
      </footer>
    </section>
  );
}

window.ConditionPanel = ConditionPanel;
