/* ============================================================
   Elcoria — Scenario script
   Simulated incoming triage call (Hungarian healthcare hotline)
   ============================================================ */

// Patient mood evolves: neutral → concerned → anxious → fearful
// Predicted condition crystallizes as more clinical signal arrives.

window.SCENARIO = {
  session: "SES-2026-05-21-0317",
  caller: "Anon. caller, female, ~55y est.",
  steps: [
    // t in seconds (since record start) — when this event should fire
    { t: 0.4, kind: "partial",  uid: "u1", text: "Jó napot…" },
    { t: 1.2, kind: "final",    uid: "u1",
      text: "Jó napot kívánok, doktornő.",
      en: "Good day, doctor.",
      mood: { neutral: 0.78, anxious: 0.12, sad: 0.06, fearful: 0.02, happy: 0.02 },
      label: "neutral",
      confidence: 0.81,
      tokens: [{ t: "Jó napot kívánok, doktornő." }],
      bio: { pitch_mean: 152, pitch_std: 18.4, jitter: 0.011, shimmer: 0.052, hnr: 18.2, energy: 0.12 },
    },

    { t: 3.6, kind: "partial",  uid: "u2", text: "Tegnap reggel óta…" },
    { t: 5.3, kind: "final",    uid: "u2",
      text: "Tegnap reggel óta nem érzem jól magam.",
      en: "I haven't felt well since yesterday morning.",
      mood: { neutral: 0.42, anxious: 0.41, sad: 0.10, fearful: 0.05, happy: 0.02 },
      label: "anxious",
      confidence: 0.74,
      tokens: [
        { t: "Tegnap reggel óta " },
        { t: "nem érzem jól magam", tag: "symptom", title: "Self-reported malaise" },
        { t: "." },
      ],
      bio: { pitch_mean: 164, pitch_std: 24.1, jitter: 0.014, shimmer: 0.063, hnr: 16.0, energy: 0.14 },
    },

    { t: 7.4, kind: "partial",  uid: "u3", text: "Fáj a mellkasom…" },
    { t: 9.6, kind: "final",    uid: "u3",
      text: "Fáj a mellkasom és néha nehezen kapok levegőt.",
      en: "My chest hurts and sometimes I have trouble breathing.",
      mood: { neutral: 0.18, anxious: 0.62, sad: 0.08, fearful: 0.10, happy: 0.02 },
      label: "anxious",
      confidence: 0.88,
      tokens: [
        { t: "Fáj a " },
        { t: "mellkasom", tag: "symptom", title: "Chest pain" },
        { t: " és néha " },
        { t: "nehezen kapok levegőt", tag: "symptom", title: "Dyspnea / breathlessness" },
        { t: "." },
      ],
      bio: { pitch_mean: 178, pitch_std: 34.7, jitter: 0.018, shimmer: 0.074, hnr: 14.1, energy: 0.17 },
    },

    { t: 11.5, kind: "partial", uid: "u4", text: "Most is olyan szorító…" },
    { t: 13.8, kind: "final",   uid: "u4",
      text: "Most is olyan szorító érzés van benne, kérem mondja meg mi lehet ez.",
      en: "Right now there's this tight feeling in it — please tell me what this could be.",
      mood: { neutral: 0.10, anxious: 0.66, sad: 0.06, fearful: 0.16, happy: 0.02 },
      label: "anxious",
      confidence: 0.91,
      tokens: [
        { t: "Most is olyan " },
        { t: "szorító érzés", tag: "symptom", title: "Constricting / tight sensation — angina-like" },
        { t: " van benne, kérem mondja meg mi lehet ez." },
      ],
      bio: { pitch_mean: 188, pitch_std: 41.2, jitter: 0.021, shimmer: 0.082, hnr: 12.8, energy: 0.19 },
    },

    { t: 15.7, kind: "partial", uid: "u5", text: "Édesanyám is…" },
    { t: 18.2, kind: "final",   uid: "u5",
      text: "Édesanyám is szívinfarktusban halt meg, nagyon félek.",
      en: "My mother also died of a heart attack — I'm very afraid.",
      mood: { neutral: 0.04, anxious: 0.30, sad: 0.10, fearful: 0.54, happy: 0.02 },
      label: "fearful",
      confidence: 0.93,
      tokens: [
        { t: "Édesanyám is " },
        { t: "szívinfarktusban halt meg", tag: "risk", title: "Family history of MI" },
        { t: ", " },
        { t: "nagyon félek", tag: "risk", title: "Patient distress" },
        { t: "." },
      ],
      bio: { pitch_mean: 196, pitch_std: 48.3, jitter: 0.024, shimmer: 0.089, hnr: 11.4, energy: 0.20 },
    },

    { t: 20.2, kind: "partial", uid: "u6", text: "Mit csináljak? Mentőt hívjak?" },
    { t: 22.0, kind: "final",   uid: "u6",
      text: "Mit csináljak? Mentőt hívjak?",
      en: "What should I do? Should I call an ambulance?",
      mood: { neutral: 0.04, anxious: 0.28, sad: 0.06, fearful: 0.60, happy: 0.02 },
      label: "fearful",
      confidence: 0.95,
      tokens: [
        { t: "Mit csináljak? " },
        { t: "Mentőt hívjak?", tag: "crisis", title: "Patient asking for emergency dispatch" },
      ],
      bio: { pitch_mean: 204, pitch_std: 52.6, jitter: 0.026, shimmer: 0.094, hnr: 10.7, energy: 0.22 },
    },
  ],

  // Questions appear as evidence mounts. Tied to step index where they unlock.
  questions: [
    { after: 2, p: "med",  hu: "Mennyi ideje tartanak a tünetek pontosan?", en: "How long exactly have the symptoms lasted?", tags: ["onset"] },
    { after: 2, p: "high", hu: "Kisugárzik-e a fájdalom a karba, vállba vagy állkapocsba?", en: "Does the pain radiate to the arm, shoulder or jaw?", tags: ["cardiac", "diagnostic"] },
    { after: 2, p: "high", hu: "Tapasztal-e izzadást, hányingert vagy szédülést?", en: "Are you experiencing sweating, nausea or dizziness?", tags: ["cardiac"] },
    { after: 4, p: "high", hu: "Hány éves Ön, és van-e ismert szívbetegsége?", en: "How old are you, and do you have any known heart conditions?", tags: ["history"] },
    { after: 4, p: "med",  hu: "Szed-e jelenleg vérnyomáscsökkentőt vagy véralvadásgátlót?", en: "Are you currently taking any blood pressure or anticoagulant medication?", tags: ["meds"] },
    { after: 5, p: "high", hu: "Egyedül van most? Van a közelben olyan, aki tudna segíteni?", en: "Are you alone right now? Is there anyone nearby who can help?", tags: ["safety"] },
    { after: 5, p: "low",  hu: "Meg tudná pontosan mondani a tartózkodási helyét?", en: "Can you tell me your exact location?", tags: ["dispatch"] },
  ],

  // Condition prediction trajectory
  // Each entry activates after step index N completes.
  predictions: [
    {
      after: 1,
      name: "Insufficient signal",
      icd: "—",
      level: 1,
      level_label: "Routine",
      confidence: 0.12,
      reasoning: "Greeting only — no clinical content yet.",
      differential: [],
    },
    {
      after: 2,
      name: "Nonspecific malaise",
      icd: "R53",
      level: 2,
      level_label: "Concerned",
      confidence: 0.34,
      reasoning: "Patient reports generalized indisposition since the previous day. Anxious prosody (rising pitch variance) but no localized symptom.",
      differential: [
        { name: "Viral syndrome", icd: "B34.9", pct: 0.22 },
        { name: "Anxiety reaction", icd: "F41.9", pct: 0.18 },
        { name: "Fatigue, unspecified", icd: "R53", pct: 0.15 },
      ],
    },
    {
      after: 3,
      name: "Possible cardiopulmonary discomfort",
      icd: "R07.4 + R06.0",
      level: 3,
      level_label: "Urgent",
      confidence: 0.62,
      reasoning: "Chest pain + intermittent dyspnea. Vocal jitter and shimmer trending upward (HNR 14.1 dB, ↓ from 18.2). Pattern consistent with anginal complaint under autonomic stress.",
      differential: [
        { name: "Stable angina", icd: "I20.8", pct: 0.34 },
        { name: "Panic attack", icd: "F41.0", pct: 0.21 },
        { name: "GERD with chest pain", icd: "K21.0", pct: 0.13 },
      ],
    },
    {
      after: 4,
      name: "Suspected acute coronary syndrome",
      icd: "I24.9",
      level: 4,
      level_label: "Crisis",
      confidence: 0.78,
      reasoning: "Constricting (\u201cszorító\u201d) chest sensation is high-specificity for ischemia. Persistent dyspnea, vocal strain (HNR 12.8 dB), elevated jitter (2.1%). Acute cardiac event must be ruled out.",
      differential: [
        { name: "Unstable angina", icd: "I20.0", pct: 0.41 },
        { name: "NSTEMI", icd: "I21.4", pct: 0.27 },
        { name: "Panic disorder", icd: "F41.0", pct: 0.18 },
      ],
    },
    {
      after: 5,
      name: "Suspected ACS — positive family history",
      icd: "I24.9",
      level: 4,
      level_label: "Crisis",
      confidence: 0.86,
      reasoning: "First-degree relative MI history significantly elevates prior probability. Patient distress accelerating (fearful 0.54). Recommend immediate EMS dispatch and ECG on arrival.",
      differential: [
        { name: "Unstable angina", icd: "I20.0", pct: 0.39 },
        { name: "NSTEMI", icd: "I21.4", pct: 0.34 },
        { name: "Acute panic episode", icd: "F41.0", pct: 0.15 },
      ],
    },
    {
      after: 6,
      name: "ACS — dispatch recommended",
      icd: "I24.9",
      level: 4,
      level_label: "Crisis",
      confidence: 0.91,
      reasoning: "Patient is requesting emergency services. Sustained fearful prosody, vocal HNR 10.7 dB (severely degraded). Family history positive. ESC guideline: dispatch ALS immediately, advise 300 mg aspirin if not contraindicated.",
      differential: [
        { name: "Unstable angina", icd: "I20.0", pct: 0.38 },
        { name: "NSTEMI / STEMI", icd: "I21", pct: 0.41 },
        { name: "Acute panic episode", icd: "F41.0", pct: 0.11 },
      ],
    },
  ],
};
