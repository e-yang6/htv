import React, { useState, useEffect, useRef, useCallback } from "react";
import { createRoot } from "react-dom/client";
import ModulesTab from "./ModulesTab";
import OnboardingTerminal from "./OnboardingTerminal";
import "./styles.css";

const API = "/api";
const ROBOT = "/robot";
const BLE_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214";
const FALL_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214";
const GFORCE_CHAR_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214";
const MAX_G_POINTS = 60;

const TRACES = [
  "M200 150 V0",
  "M200 150 V90 H55 V0",
  "M200 150 V90 H135 V0",
  "M200 150 V100 H290 V0",
  "M200 150 V100 H350 V50 H400",
  "M200 150 H310 V70 H400",
  "M200 150 H400",
  "M200 150 H310 V230 H400",
  "M200 150 V300",
  "M200 150 V210 H110 V300",
  "M200 150 V210 H300 V300",
  "M200 150 H90 V60 H0",
  "M200 150 H0",
  "M200 150 H90 V245 H0",
];

function GForceChart({ data, max = 4 }) {
  const w = 280, h = 80, pad = 2;
  if (!data.length) return <div style={{ height: 80 }} />;
  const pts = data.map((v, i) => {
    const x = pad + (i / Math.max(data.length - 1, 1)) * (w - pad * 2);
    const y = h - pad - (Math.min(v, max) / max) * (h - pad * 2);
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height: 80 }}>
      <polyline points={pts} fill="none" stroke="#18bff4" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

const EMERGENCY_INSTRUCTIONS = {
  "Severe Peanut Allergy": [
    "Locate the EpiPen on the robot's arm module",
    "Remove the blue safety cap",
    "Press the orange tip firmly against the outer thigh",
    "Hold for 10 seconds, then remove",
    "Call 911 immediately",
    "Place them in recovery position on their side",
  ],
  "Type 1 Diabetes": [
    "Check if they are conscious and responsive",
    "If conscious, give them sugar — juice, candy, or glucose tabs",
    "If unconscious, do NOT put anything in their mouth",
    "Place them in recovery position on their side",
    "Call 911 immediately",
    "Monitor breathing until help arrives",
  ],
  "Severe Asthma": [
    "Help them sit upright — do not lay them down",
    "Check the robot's arm for an inhaler module",
    "Help them take 1 puff, wait 30 seconds, repeat up to 4 puffs",
    "Keep them calm and encourage slow breathing",
    "Call 911 if no improvement after 4 puffs",
    "Do not leave them alone",
  ],
  "Cardiac History / Pacemaker Alert": [
    "Call 911 immediately — mention pacemaker",
    "If unconscious and not breathing, begin CPR",
    "If an AED is nearby, use it — it will detect the pacemaker",
    "Do NOT place AED pads directly over the pacemaker bump",
    "Place them flat on their back on a hard surface",
    "Continue CPR until paramedics arrive",
  ],
};

const DEFAULT_INSTRUCTIONS = [
  "Call 911 immediately",
  "Check if the person is conscious and breathing",
  "Place them in recovery position on their side",
  "Keep them warm and comfortable",
  "Do not move them unless they are in danger",
  "Stay with them until help arrives",
];

function Stat({ label, value, hint, accent = false }) {
  return (
    <div className="min-w-0">
      <dt className="micro mb-2">{label}</dt>
      <dd className={`stat-value ${accent ? "text-cyan" : ""}`}>{value}{hint && <small className="micro mt-2 block text-zinc-600">{hint}</small>}</dd>
    </div>
  );
}

function App() {
  const [tab, setTab] = useState("camera");

  const [isOnboardingOpen, setIsOnboardingOpen] = useState(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.has("onboard") || params.has("reset")) return true;
      return sessionStorage.getItem("ironheart_session_onboarded") !== "true";
    } catch {
      return true;
    }
  });

  const [hostCondition, setHostCondition] = useState(() => {
    try {
      return localStorage.getItem("ironheart_host_condition") || "";
    } catch {
      return "";
    }
  });
  // For a condition typed in by hand during onboarding: its description and the helper's steps
  const [hostProfile, setHostProfile] = useState(() => {
    try {
      return { description: "", steps: [], ...JSON.parse(localStorage.getItem("ironheart_host_profile") || "{}") };
    } catch {
      return { description: "", steps: [] };
    }
  });
  // Full-screen "what to do" page, shown once the bystander says yes
  const [showInstructions, setShowInstructions] = useState(false);


  const [backendOnline, setBackendOnline] = useState(false);
  const [status, setStatus] = useState(null);
  const [gforceHistory, setGforceHistory] = useState([]);
  const [falls, setFalls] = useState([]);
  const [personCount, setPersonCount] = useState(0);
  const [activityLevel, setActivityLevel] = useState("—");
  const [currentG, setCurrentG] = useState(1.0);

  const [bleConnected, setBleConnected] = useState(false);
  const [bleConnecting, setBleConnecting] = useState(false);
  const bleDeviceRef = useRef(null);

  const [localFalls, setLocalFalls] = useState([]);
  const localGRef = useRef([]);
  const fallWaitRef = useRef(false);
  const fallStartRef = useRef(null);
  const impactRef = useRef(1.0);

  const [robotOnline, setRobotOnline] = useState(false);
  const [robotStatus, setRobotStatus] = useState(null);

  const [feedError, setFeedError] = useState(false);
  const [localCamera, setLocalCamera] = useState(false);
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  const [banner, setBanner] = useState(null);

  // Voice messages
  const emergencyAudio = useRef(new Audio("/emergency.ogg"));
  const ownerFellAudio = useRef(new Audio("/owner-fell.ogg"));
  const willingAudio = useRef(new Audio("/willing-to-help.ogg"));
  const lastRobotMode = useRef(null);
  const arrivalPlayed = useRef(false);

  useEffect(() => {
    emergencyAudio.current.loop = true;
    // Browsers only allow sound after the page has been clicked/tapped once: on the first click,
    // play-and-pause each clip so later alerts (with nobody touching the page) can play
    const unlock = () => {
      for (const a of [emergencyAudio, ownerFellAudio, willingAudio]) {
        a.current.muted = true;
        a.current.play().then(() => { a.current.pause(); a.current.muted = false; a.current.currentTime = 0; })
          .catch(() => { a.current.muted = false; });
      }
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
    window.addEventListener("pointerdown", unlock);
    window.addEventListener("keydown", unlock);
    return () => { window.removeEventListener("pointerdown", unlock); window.removeEventListener("keydown", unlock); };
  }, []);

  useEffect(() => {
    const mode = robotStatus?.mode;
    const prev = lastRobotMode.current;
    lastRobotMode.current = mode;

    // Looking for a person to bring back: loop the call for help the whole time (re-tried on every
    // status update, so it starts even if an earlier play() was blocked)
    if (mode === "seeking" || mode === "scanning") {
      arrivalPlayed.current = false;
      if (prev !== "seeking" && prev !== "scanning") emergencyAudio.current.currentTime = 0;
      if (emergencyAudio.current.paused) emergencyAudio.current.play().catch(() => {});
    } else {
      emergencyAudio.current.pause();
    }

    if (mode === "arrived" && !arrivalPlayed.current) {
      arrivalPlayed.current = true;
      ownerFellAudio.current.currentTime = 0;
      ownerFellAudio.current.play().catch(() => {});
      ownerFellAudio.current.onended = () => {
        setTimeout(() => {
          willingAudio.current.currentTime = 0;
          willingAudio.current.play().catch(() => {});
        }, 800);
      };
    }

    if (!mode || mode === "follow") {
      arrivalPlayed.current = false;
      emergencyAudio.current.pause();
      ownerFellAudio.current.pause();
      willingAudio.current.pause();
    }
  }, [robotStatus]);

  // Backend polling
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const [s, g, fl] = await Promise.all([
          fetch(API + "/status").then(r => r.json()),
          fetch(API + "/gforce").then(r => r.json()),
          fetch(API + "/falls").then(r => r.json()),
        ]);
        setBackendOnline(true);
        setStatus(s);
        setPersonCount(s.person_count);
        setFalls(fl);
        if (!bleConnected) {
          setCurrentG(s.current_g);
          setActivityLevel(s.activity_level);
          setGforceHistory(g.values || []);
          if (s.emergency) {
            const condText = hostCondition || s.host_condition || "an urgent medical condition";
            setBanner({ type: "crit", text: `Emergency — Host Condition: ${condText} — seeking nearest person (${s.direction || "scanning"})` });
          } else {
            if (s.fall_waiting) setBanner({ type: "warn", text: "Fall detected — waiting for response" });
            else setBanner(null);
          }

          if (s.host_condition && s.host_condition !== "Not specified" && !hostCondition) {
            setHostCondition(s.host_condition);
          }
        }
        if (feedError && !localCamera) setFeedError(false);
      } catch {
        setBackendOnline(false);
        if (!bleConnected) setFeedError(true);
      }
    }, 800);
    return () => clearInterval(id);
  }, [bleConnected, feedError, localCamera, hostCondition]);

  // Robot polling
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const s = await fetch(ROBOT + "/status").then(r => r.json());
        setRobotOnline(true);
        setRobotStatus(s);
      } catch {
        setRobotOnline(false);
        setRobotStatus(null);
      }
    }, 500);
    return () => clearInterval(id);
  }, []);

  // BLE
  const connectBLE = useCallback(async () => {
    if (!navigator.bluetooth) { alert("Web Bluetooth not supported. Use Chrome or Edge."); return; }
    setBleConnecting(true);
    try {
      const device = await navigator.bluetooth.requestDevice({
        filters: [{ name: "FallDetector" }],
        optionalServices: [BLE_SERVICE_UUID],
      });
      bleDeviceRef.current = device;
      device.addEventListener("gattserverdisconnected", () => {
        setBleConnected(false);
        setBleConnecting(false);
        setBanner(null);
      });
      const server = await device.gatt.connect();
      const service = await server.getPrimaryService(BLE_SERVICE_UUID);

      const fallChar = await service.getCharacteristic(FALL_CHAR_UUID);
      await fallChar.startNotifications();
      fallChar.addEventListener("characteristicvaluechanged", (e) => {
        const val = e.target.value.getUint8(0);
        const now = Date.now();
        if (val === 0) {
          if (fallWaitRef.current && fallStartRef.current) {
            setLocalFalls(p => [...p, { time_str: new Date().toLocaleTimeString(), impact_g: impactRef.current, outcome: "cancelled", response_ms: now - fallStartRef.current }]);
          }
          fallWaitRef.current = false;
          fallStartRef.current = null;
          setBanner(null);
          fetch(API + "/simulate/reset").catch(() => {});
        } else if (val === 1) {
          fallWaitRef.current = true;
          fallStartRef.current = now;
          setBanner({ type: "warn", text: "Fall detected — waiting for response (double-tap chest piece)" });
          fetch(API + "/simulate/fall").catch(() => {});
        } else if (val === 2) {
          const ms = fallStartRef.current ? (now - fallStartRef.current) : 5000;
          setLocalFalls(p => [...p, { time_str: new Date().toLocaleTimeString(), impact_g: impactRef.current, outcome: "emergency", response_ms: ms }]);
          fallWaitRef.current = false;
          fallStartRef.current = null;
          const condText = hostCondition || "an urgent medical condition";
          setBanner({ type: "crit", text: `EMERGENCY — Host Condition: ${condText} — No response — Robot dispatched!` });
          fetch(API + "/simulate/emergency").catch(() => {});
        }
      });

      try {
        const gChar = await service.getCharacteristic(GFORCE_CHAR_UUID);
        await gChar.startNotifications();
        gChar.addEventListener("characteristicvaluechanged", (e) => {
          const g = e.target.value.getUint16(0, true) / 100.0;
          impactRef.current = g;
          setCurrentG(g);
          localGRef.current.push(g);
          if (localGRef.current.length > MAX_G_POINTS) localGRef.current.shift();
          setGforceHistory([...localGRef.current]);
          if (localGRef.current.length >= 10) {
            const r = localGRef.current.slice(-30);
            const avg = r.reduce((a, b) => a + b, 0) / r.length;
            const v = r.reduce((a, b) => a + Math.pow(b - avg, 2), 0) / r.length;
            setActivityLevel(v > 0.15 ? "high" : v > 0.03 ? "medium" : "low");
          }
        });
      } catch {}

      setBleConnected(true);
      setBleConnecting(false);
    } catch (err) {
      setBleConnected(false);
      setBleConnecting(false);
      if (err.name !== "NotFoundError") alert("BLE error: " + err.message);
    }
  }, []);

  const toggleWebcam = useCallback(async () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
      setLocalCamera(false);
      return;
    }
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } } });
      streamRef.current = s;
      if (videoRef.current) videoRef.current.srcObject = s;
      setLocalCamera(true);
    } catch (err) { alert("Could not access webcam: " + err.message); }
  }, []);

  const toggleSeek = useCallback(async () => {
    try { setRobotStatus(await fetch(ROBOT + "/seek", { method: "POST" }).then(r => r.json())); }
    catch { setRobotStatus(null); }
  }, []);

  const confirmRobot = useCallback(async () => {
    try { setRobotStatus(await fetch(ROBOT + "/confirm", { method: "POST" }).then(r => r.json())); }
    catch {}
  }, []);

  const rejectRobot = useCallback(async () => {
    try { setRobotStatus(await fetch(ROBOT + "/reject", { method: "POST" }).then(r => r.json())); }
    catch {}
  }, []);

  // Click-to-follow: click a person in the robot camera feed to lock on; click empty space to clear
  const selectFollow = useCallback(async (e) => {
    const img = e.currentTarget;
    const rect = img.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width, y = (e.clientY - rect.top) / rect.height;
    try { setRobotStatus(await fetch(`${ROBOT}/select?x=${x.toFixed(3)}&y=${y.toFixed(3)}`, { method: "POST" }).then(r => r.json())); }
    catch {}
  }, []);

  const resetRobotCamera = useCallback(() => {
    fetch(ROBOT + "/camera-reset", { method: "POST" }).catch(() => {});
  }, []);

  const activeFalls = bleConnected ? localFalls : falls;
  const fallCount = activeFalls.length;
  const bleLabel = bleConnected ? "Connected" : bleConnecting ? "Scanning..." : status?.ble_connected ? "Server BLE" : "Off";
  const videoSrc = localCamera ? null : backendOnline ? API + "/video" : robotOnline ? ROBOT + "/video" : null;

  const robotLabel = (() => {
    if (!robotOnline || !robotStatus) return { text: "Robot offline", disabled: true };
    const m = { follow: "Go to nearest person", seeking: "Heading to person", scanning: "Looking for person", arrived: "Arrived — return", returning: "Returning..." };
    return { text: m[robotStatus.mode] || robotStatus.mode, disabled: robotStatus.mode === "follow" && !robotStatus.camera };
  })();

  // What follow mode is steering by (sticker on your pants > clicked person > chest-sensor gyro)
  const followLabel = !robotStatus ? null
    : robotStatus.following === "sticker" ? "Following sticker"
    : robotStatus.following === "person" ? "Following clicked person"
    : "Following chest sensor · click a person to lock on";

  // Test button: show the "will you help?" screen (with its voice clips) without the robot
  const [testConfirm, setTestConfirm] = useState(false);
  const startTestConfirm = () => {
    setTestConfirm(true);
    ownerFellAudio.current.currentTime = 0;
    ownerFellAudio.current.play().catch(() => {});
    ownerFellAudio.current.onended = () => setTimeout(() => {
      willingAudio.current.currentTime = 0;
      willingAudio.current.play().catch(() => {});
    }, 800);
  };
  const endTestConfirm = () => {
    setTestConfirm(false);
    ownerFellAudio.current.onended = null;
    ownerFellAudio.current.pause();
    willingAudio.current.pause();
  };
  const showConfirm = robotStatus?.awaiting_confirm || testConfirm;
  const isEmergency = status?.emergency || banner?.type === "crit";
  const instructions = EMERGENCY_INSTRUCTIONS[hostCondition]
    || (hostProfile.steps?.length ? hostProfile.steps : DEFAULT_INSTRUCTIONS);

  return (
    <div className="min-h-screen bg-[#090b0f] text-zinc-100">

      {showConfirm && (
        <div className="confirm-screen" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
          <p className="confirm-tag">{testConfirm ? "TEST — " : ""}EMERGENCY</p>
          <h1 id="confirm-title" className="confirm-title">Someone nearby has fallen</h1>
          <p className="confirm-condition">They have {hostCondition || "an urgent medical condition"}</p>
          <p className="confirm-question">This robot can lead you to them. Will you follow?</p>
          <div className="confirm-actions">
            <button onClick={() => { (testConfirm ? endTestConfirm : confirmRobot)(); setShowInstructions(true); }} className="confirm-btn confirm-yes">YES, LEAD ME</button>
            <button onClick={testConfirm ? endTestConfirm : rejectRobot} className="confirm-btn">No</button>
          </div>
        </div>
      )}

      {showInstructions && !showConfirm && (
        <div className="instr-screen" role="dialog" aria-modal="true" aria-labelledby="instr-title">
          <p className="instr-tag">FOLLOW THE ROBOT — IT WILL TAKE YOU TO THEM</p>
          <h1 id="instr-title" className="instr-title">What to do when you get there</h1>
          <p className="instr-condition">They have {hostCondition || "an urgent medical condition"}</p>
          {hostProfile.description && !EMERGENCY_INSTRUCTIONS[hostCondition] && (
            <p className="instr-description">{hostProfile.description}</p>
          )}
          <ol className="instr-steps">
            {instructions.map((step, i) => <li key={i}>{step}</li>)}
          </ol>
          <button className="instr-close" onClick={() => setShowInstructions(false)}>Close</button>
        </div>
      )}

      <div className="mx-auto min-h-screen max-w-6xl px-3 py-3 sm:px-6 sm:py-6">

        <header className="mb-4 flex items-center justify-between px-1 sm:mb-6">
          <h1 className="text-sm font-semibold tracking-[0.22em] sm:text-base">IRONHEART</h1>
          <button
            onClick={() => setIsOnboardingOpen(true)}
            className="border border-line px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-cyan hover:text-cyan"
            title="Click to view or update host medical condition"
          >
            Host: {hostCondition ? hostCondition.split(" (")[0] : "Not Set"}
          </button>
        </header>

        {banner && (
          <p className={`banner ${banner.type === "crit" ? "banner-crit" : "banner-warn"}`}>{banner.text}</p>
        )}

        <main className="grid gap-4 lg:grid-cols-2 lg:gap-5">
          {/* LEFT — Heart + Circuit Board */}
          <section className="panel relative flex items-center justify-center p-4 sm:p-5">
            <svg className="circuit-svg" viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice">
              <defs>
                <filter id="glow"><feGaussianBlur stdDeviation="3"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>
              </defs>
              {TRACES.map((d, i) => <path key={"b"+i} d={d} className="cb-base" />)}
              {TRACES.map((d, i) => <path key={"p"+i} d={d} pathLength="100" className="cb-pulse" />)}
            </svg>
            <div className={`heart-stage ${isEmergency ? "opacity-10" : ""} transition-opacity duration-500`}>
              <div className="heart-aura" />
              <img src="/heart.png" alt="" className="heart-art" />
            </div>
            {isEmergency && (
              <div className="absolute inset-0 z-10 flex flex-col justify-center p-5 sm:p-8">
                <div className="micro text-red-400 font-semibold mb-1">EMERGENCY — {hostCondition || "UNKNOWN CONDITION"}</div>
                <div className="text-sm font-semibold text-zinc-100 mb-3">What to do:</div>
                <ol className="space-y-2">
                  {instructions.map((step, i) => (
                    <li key={i} className="flex gap-2 text-xs text-zinc-300 leading-relaxed">
                      <span className="shrink-0 text-cyan font-mono">{i + 1}.</span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </section>

          {/* RIGHT — Camera */}
          <section className="panel overflow-hidden">
            <nav className="flex border-b border-line">
              {[["camera", "Camera"], ["log", "Falls"], ["modules", "Modules"]].map(([id, label]) => (
                <button key={id} onClick={() => setTab(id)} className={`tab ${tab === id ? "tab-active" : ""}`}>{label}</button>
              ))}
            </nav>
            {tab === "camera" ? (
              <figure className="m-0 p-3">
                {localCamera ? (
                  <video ref={videoRef} autoPlay playsInline className="w-full" />
                ) : videoSrc ? (
                  <>
                    <img src={videoSrc} alt="Robot camera" className="w-full cursor-crosshair" onClick={selectFollow}
                         onError={() => setFeedError(true)} />
                    <figcaption className="feed-caption">
                      <span>{followLabel}</span>
                      <button onClick={resetRobotCamera} className="hover:text-cyan">Reset camera</button>
                    </figcaption>
                  </>
                ) : (
                  <figcaption className="py-24 text-center text-xs text-zinc-500">Backend video stream offline</figcaption>
                )}
              </figure>
            ) : tab === "log" ? (
              activeFalls.length === 0 ? (
                <p className="p-6 text-center text-xs text-zinc-500">No falls detected</p>
              ) : (
                <table className="fall-log">
                  <thead><tr><th>Time</th><th>Event</th><th>Impact</th><th>Response</th></tr></thead>
                  <tbody>
                    {[...activeFalls].reverse().map((f, i) => (
                      <tr key={i}>
                        <td>{f.time_str}</td>
                        <td className={f.outcome === "emergency" ? "text-red-400" : "text-emerald-400"}>
                          {f.outcome === "emergency" ? "Emergency alert" : "Fall cancelled"}
                        </td>
                        <td>{f.impact_g ? f.impact_g.toFixed(2) + "g" : "—"}</td>
                        <td>{(f.response_ms / 1000).toFixed(1)}s</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            ) : (
              <ModulesTab
                backendOnline={backendOnline}
                apiBase={API}
                robotState={status}
                onNotification={(n) => setBanner(n)}
              />
            )}
          </section>

          {/* BOTTOM — Stats spanning full width */}
          <section className="panel p-4 sm:p-5 lg:col-span-2">
            <dl className="grid grid-cols-3 gap-3 border-b border-[#242832] pb-3">
              <div>
                <dt className="micro">G-FORCE</dt>
                <dd className="gforce" style={currentG > 1.5 ? { color: "#ef4444" } : {}}>{currentG.toFixed(2)}<span className="text-2xl">g</span></dd>
              </div>
              <Stat label="BLE" value={bleLabel} hint={bleConnected ? "Web BLE" : backendOnline ? "server" : null} accent={bleConnected || status?.ble_connected} />
              <Stat label="ROBOT" value={robotOnline ? "Online" : "Offline"}
                    hint={robotStatus ? (robotStatus.mode === "follow" ? `${robotStatus.following} · ${robotStatus.follow_state}` : robotStatus.mode) : null}
                    accent={robotOnline} />
            </dl>
            <GForceChart data={gforceHistory.slice(-MAX_G_POINTS)} />

            <div className="mt-5 grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-7">
              <button className="action-button py-2" onClick={connectBLE}>{bleConnected ? "BLE OK" : "CONNECT BLE"}</button>
              <button className="action-button py-2" onClick={toggleWebcam}>{localCamera ? "STOP CAM" : "LOCAL CAM"}</button>
              <button className="action-button py-2" onClick={() => fetch(API + "/simulate/fall").catch(() => {})}>SIM FALL</button>
              <button
                className="action-button py-2"
                onClick={() => {
                  fetch(API + "/simulate/emergency").catch(() => {});
                  const condText = hostCondition || "an urgent medical condition";
                  setBanner({ type: "crit", text: `Emergency — Host Condition: ${condText}` });
                }}
              >
                SIM EMERGENCY
              </button>
              <button
                className="action-button py-2"
                onClick={() => {
                  fetch(API + "/simulate/reset").catch(() => {});
                  setBanner(null);
                }}
              >
                RESET
              </button>
              <button className="action-button py-2" onClick={toggleSeek} disabled={robotLabel.disabled} style={!robotOnline ? { opacity: 0.4 } : {}} title={robotLabel.text}>
                {robotStatus && robotStatus.mode !== "follow" ? "RETURN" : "FIND HELP"}
              </button>
              <button className="action-button py-2" onClick={startTestConfirm} title="Preview the screen a bystander sees when the robot reaches them">TEST HELP</button>
            </div>
          </section>

        </main>

        <OnboardingTerminal
          apiBase={API}
          isOpen={isOnboardingOpen}
          onClose={() => setIsOnboardingOpen(false)}
          onConditionSet={(c, profile) => { setHostCondition(c); if (profile) setHostProfile(profile); }}
        />

      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
