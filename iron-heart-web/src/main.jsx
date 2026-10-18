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


function GForceChart({ data, max = 4 }) {
  const w = 280, h = 80, pad = 2;
  if (!data.length) return <svg className="chart" />;
  const pts = data.map((v, i) => {
    const x = pad + (i / Math.max(data.length - 1, 1)) * (w - pad * 2);
    const y = h - pad - (Math.min(v, max) / max) * (h - pad * 2);
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="chart" preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
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

function Stat({ label, value, hint }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className="num">{value}{hint && <small>{hint}</small>}</dd>
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
  const cancelled = activeFalls.filter(x => x.outcome === "cancelled");
  const avgResp = cancelled.length ? (cancelled.reduce((a, x) => a + x.response_ms, 0) / cancelled.length / 1000).toFixed(1) + "s" : "—";
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

  const showConfirm = robotStatus?.awaiting_confirm;
  const isEmergency = status?.emergency || banner?.type === "crit";
  const instructions = EMERGENCY_INSTRUCTIONS[hostCondition] || DEFAULT_INSTRUCTIONS;

  const wearerState = status?.emergency ? ["crit", "Emergency"]
    : status?.fall_waiting ? ["warn", "Fall detected"]
    : backendOnline ? ["ok", "Normal"] : ["none", "No data"];
  const robotHint = !robotStatus ? null
    : robotStatus.mode === "follow" ? `${robotStatus.following} · ${robotStatus.follow_state}` : robotStatus.mode;

  return (
    <div className="app">
      {showConfirm && (
        <div className="backdrop">
          <div className="dialog" role="dialog" aria-modal="true">
            <h2>Someone nearby has fallen</h2>
            <p>This robot can lead you to them. Will you follow?</p>
            <div className="row">
              <button onClick={rejectRobot} className="btn">No</button>
              <button onClick={confirmRobot} className="btn btn-primary">Yes, lead me</button>
            </div>
          </div>
        </div>
      )}

      <header className="top">
        <h1>Ironheart</h1>
        <button className="link" onClick={() => setIsOnboardingOpen(true)} title="View or change the host's medical condition">
          Host condition: {hostCondition ? hostCondition.split(" (")[0] : "not set"}
        </button>
      </header>

      {banner && <p className={`alert alert-${banner.type === "crit" ? "crit" : "warn"}`}>{banner.text}</p>}

      <main className="layout">
        <section>
          <div className="wearer">
            <img src="/heart.png" alt="" className={`heart ${isEmergency ? "alarm" : ""}`} />
            <div>
              <h2>Wearer</h2>
              <p className={`state state-${wearerState[0]}`}>{wearerState[1]}</p>
            </div>
          </div>
          {isEmergency && (
            <>
              <h2>What to do — {hostCondition || "unknown condition"}</h2>
              <ol className="steps">{instructions.map((step, i) => <li key={i}>{step}</li>)}</ol>
            </>
          )}

          <h2>G-force</h2>
          <p className="gforce num" style={currentG > 1.5 ? { color: "var(--red)" } : undefined}>{currentG.toFixed(2)} g</p>
          <GForceChart data={gforceHistory.slice(-MAX_G_POINTS)} />

          <dl className="stats">
            <Stat label="People in view" value={personCount} />
            <Stat label="Activity" value={activityLevel} />
            <Stat label="BLE" value={bleLabel} hint={bleConnected ? "Web BLE" : backendOnline ? "server" : null} />
            <Stat label="Falls" value={fallCount} />
            <Stat label="Avg response" value={avgResp} hint="cancelled falls" />
            <Stat label="Robot" value={robotOnline ? "Online" : "Offline"} hint={robotHint} />
          </dl>
        </section>

        <section>
          <nav className="tabs" role="tablist">
            {[["camera", "Camera"], ["log", "Falls"], ["modules", "Modules"]].map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>
            ))}
          </nav>
          {tab === "camera" ? (
            localCamera ? (
              <figure className="camera"><video ref={videoRef} autoPlay playsInline /></figure>
            ) : videoSrc ? (
              <figure className="camera">
                <img src={videoSrc} alt="Robot camera" onClick={selectFollow} onError={() => setFeedError(true)} />
                <figcaption>
                  <span>{followLabel}</span>
                  <button className="link" onClick={resetRobotCamera}>Reset camera</button>
                </figcaption>
              </figure>
            ) : (
              <p className="empty">Camera stream offline</p>
            )
          ) : tab === "log" ? (
            activeFalls.length === 0 ? (
              <p className="empty">No falls detected</p>
            ) : (
              <table className="num">
                <thead><tr><th>Time</th><th>Event</th><th>Impact</th><th>Response</th></tr></thead>
                <tbody>
                  {[...activeFalls].reverse().map((f, i) => (
                    <tr key={i}>
                      <td>{f.time_str}</td>
                      <td className={f.outcome === "emergency" ? "event-crit" : "event-ok"}>
                        {f.outcome === "emergency" ? "Emergency alert" : "Fall cancelled"}
                      </td>
                      <td>{f.impact_g ? f.impact_g.toFixed(2) + " g" : "—"}</td>
                      <td>{(f.response_ms / 1000).toFixed(1)} s</td>
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
      </main>

      <footer className="controls">
        <button className="btn btn-primary" onClick={toggleSeek} disabled={robotLabel.disabled} title={robotLabel.text}>
          {robotStatus && robotStatus.mode !== "follow" ? "Return" : "Find help"}
        </button>
        <button className="btn" onClick={() => fetch(API + "/simulate/fall").catch(() => {})}>Simulate fall</button>
        <button
          className="btn btn-danger"
          onClick={() => {
            fetch(API + "/simulate/emergency").catch(() => {});
            const condText = hostCondition || "an urgent medical condition";
            setBanner({ type: "crit", text: `Emergency — Host Condition: ${condText}` });
          }}
        >
          Simulate emergency
        </button>
        <button
          className="btn"
          onClick={() => {
            fetch(API + "/simulate/reset").catch(() => {});
            setBanner(null);
          }}
        >
          Reset
        </button>
        <button className="btn" onClick={connectBLE}>{bleConnected ? "BLE connected" : "Connect BLE"}</button>
        <button className="btn" onClick={toggleWebcam}>{localCamera ? "Stop local camera" : "Local camera"}</button>
      </footer>

      <OnboardingTerminal
        apiBase={API}
        isOpen={isOnboardingOpen}
        onClose={() => setIsOnboardingOpen(false)}
        onConditionSet={(c) => setHostCondition(c)}
      />
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
