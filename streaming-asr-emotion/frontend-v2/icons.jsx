/* Icons — outline, 1.6px stroke, 16x16 viewBox */

const Icon = ({ d, viewBox = "0 0 16 16", size = 14, fill = "none", strokeWidth = 1.6, children, ...rest }) => (
  <svg
    viewBox={viewBox}
    width={size}
    height={size}
    fill={fill}
    stroke="currentColor"
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    {...rest}
  >
    {d && <path d={d} />}
    {children}
  </svg>
);

const IconMic = (p) => (
  <Icon {...p}>
    <rect x="6" y="2" width="4" height="8" rx="2" />
    <path d="M3.5 7.5a4.5 4.5 0 0 0 9 0" />
    <path d="M8 12v2" />
    <path d="M5.5 14h5" />
  </Icon>
);

const IconStop = (p) => (
  <Icon {...p}>
    <rect x="4" y="4" width="8" height="8" rx="1.5" fill="currentColor" stroke="none" />
  </Icon>
);

const IconUpload = (p) => (
  <Icon {...p}>
    <path d="M8 10V3" />
    <path d="M5 5.5L8 2.5 11 5.5" />
    <path d="M3 10v2.5A1.5 1.5 0 0 0 4.5 14h7a1.5 1.5 0 0 0 1.5-1.5V10" />
  </Icon>
);

const IconWave = (p) => (
  <Icon {...p}>
    <path d="M2 8h1.5" />
    <path d="M4.5 5.5v5" />
    <path d="M7 3v10" />
    <path d="M9.5 5.5v5" />
    <path d="M12 7v2" />
    <path d="M14 8h.5" />
  </Icon>
);

const IconSun = (p) => (
  <Icon {...p}>
    <circle cx="8" cy="8" r="3" />
    <path d="M8 1.5v1.5M8 13v1.5M2.6 2.6l1.05 1.05M12.35 12.35l1.05 1.05M1.5 8H3M13 8h1.5M2.6 13.4l1.05-1.05M12.35 3.65l1.05-1.05" />
  </Icon>
);

const IconMoon = (p) => (
  <Icon {...p}>
    <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7z" />
  </Icon>
);

const IconCpu = (p) => (
  <Icon {...p}>
    <rect x="4" y="4" width="8" height="8" rx="1" />
    <rect x="6" y="6" width="4" height="4" />
    <path d="M6 1.5v2M10 1.5v2M6 12.5v2M10 12.5v2M1.5 6h2M1.5 10h2M12.5 6h2M12.5 10h2" />
  </Icon>
);

const IconBrain = (p) => (
  <Icon {...p}>
    <path d="M7 2.5a2 2 0 0 0-2 2 1.6 1.6 0 0 0-1.5 1.6c0 .5.2 1 .6 1.3-.4.3-.6.8-.6 1.3 0 .8.6 1.5 1.4 1.6A2 2 0 0 0 7 12.5V2.5z" />
    <path d="M9 2.5a2 2 0 0 1 2 2 1.6 1.6 0 0 1 1.5 1.6c0 .5-.2 1-.6 1.3.4.3.6.8.6 1.3 0 .8-.6 1.5-1.4 1.6A2 2 0 0 1 9 12.5V2.5z" />
  </Icon>
);

const IconPulse = (p) => (
  <Icon {...p}>
    <path d="M1.5 8h2.5l1.5-4 2 8 1.5-4h5" />
  </Icon>
);

const IconQuestion = (p) => (
  <Icon {...p}>
    <circle cx="8" cy="8" r="6" />
    <path d="M6.3 6a1.7 1.7 0 1 1 2.4 1.6c-.5.3-.7.6-.7 1.1V9" />
    <circle cx="8" cy="11" r="0.4" fill="currentColor" stroke="none" />
  </Icon>
);

const IconAmbulance = (p) => (
  <Icon {...p}>
    <rect x="1" y="5" width="9" height="6" rx="0.5" />
    <path d="M10 7h2.5l1.5 2v2H10z" />
    <circle cx="4" cy="12" r="1.2" />
    <circle cx="11.5" cy="12" r="1.2" />
    <path d="M5.5 8v-1.5M5.5 7.25h-1M5.5 7.25h1" />
  </Icon>
);

const IconChevron = (p) => (
  <Icon {...p}>
    <path d="M4 6l4 4 4-4" />
  </Icon>
);

const IconCheck = (p) => (
  <Icon {...p}>
    <path d="M3 8.5l3.5 3L13 5" />
  </Icon>
);

const IconClose = (p) => (
  <Icon {...p}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </Icon>
);

const IconShield = (p) => (
  <Icon {...p}>
    <path d="M8 1.5l5 1.5v4c0 3.2-2.1 6-5 7-2.9-1-5-3.8-5-7v-4l5-1.5z" />
    <path d="M6 7.5l1.5 1.5L10.5 6" />
  </Icon>
);

const IconSpark = (p) => (
  <Icon {...p}>
    <path d="M8 1.5l1.4 4.6L14 7.5l-4.6 1.4L8 13.5 6.6 8.9 2 7.5l4.6-1.4z" />
  </Icon>
);

Object.assign(window, {
  Icon,
  IconMic, IconStop, IconUpload, IconWave, IconSun, IconMoon, IconCpu, IconBrain,
  IconPulse, IconQuestion, IconAmbulance, IconChevron, IconCheck, IconClose, IconShield, IconSpark,
});
