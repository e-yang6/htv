import React, { useState, useEffect, useRef, useCallback } from "react";
import { createRoot } from "react-dom/client";
import { Camera, Terminal } from "lucide-react";
import "./styles.css";

const API = "http://localhost:5001";
const ROBOT = "http://localhost:5002";
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

function Stat({ label, value, hint, accent = false }) {
  return (
    <div className="min-w-0">
      <div className="micro mb-2">{label}</div>
      <div className={`stat-value ${accent ? "text-cyan" : ""}`}>{value}</div>
      <div className="micro mt-2 text-zinc-600">{hint}</div>
    </div>
  );
}

function App() {
  const [tab, setTab] = useState("camera");

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
          if (s.emergency) setBanner({ type: "crit", text: "Emergency — seeking nearest person (" + (s.direction || "scanning") + ")" });
          else if (s.fall_waiting) setBanner({ type: "warn", text: "Fall detected — waiting for response" });
          else setBanner(null);
        }
        if (feedError && !localCamera) setFeedError(false);
      } catch {
        setBackendOnline(false);
        if (!bleConnected) setFeedError(true);
      }
    }, 800);
    return () => clearInterval(id);
  }, [bleConnected, feedError, localCamera]);

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
          setBanner({ type: "crit", text: "EMERGENCY — No response — Robot dispatched!" });
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

  const showConfirm = robotStatus?.awaiting_confirm;

  return (
    <div className="min-h-screen bg-[#090b0f] text-zinc-100">

      {showConfirm && (
        <div className="confirm-overlay">
          <div className="confirm-box">
            <p className="text-lg font-semibold">Someone nearby has fallen</p>
            <p className="mt-2 text-sm text-zinc-400">This robot can lead you to them. Will you follow?</p>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <button onClick={rejectRobot} className="confirm-btn">No</button>
              <button onClick={confirmRobot} className="confirm-btn confirm-yes">Yes, lead me</button>
            </div>
          </div>
        </div>
      )}

      <div className="mx-auto min-h-screen max-w-6xl px-3 py-3 sm:px-6 sm:py-6">

        <header className="mb-4 px-1 sm:mb-6">
          <span className="text-sm font-semibold tracking-[0.22em] sm:text-base">IRONHEART</span>
        </header>

        {banner && (
          <div className={`mb-4 rounded-lg px-4 py-3 text-center text-sm ${banner.type === "crit" ? "bg-red-500/10 text-red-400" : "bg-amber-500/10 text-amber-300"}`}>
            {banner.text}
          </div>
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
            <div className="heart-stage">
              <div className="heart-aura" />
              <img src="/heart.png" alt="" className="heart-art" />
            </div>
          </section>

          {/* RIGHT — Camera */}
          <section className="panel overflow-hidden">
            <div className="flex border-b border-line">
              <button onClick={() => setTab("camera")} className={`tab ${tab === "camera" ? "tab-active" : ""}`}><Camera size={14} /> Camera</button>
              <button onClick={() => setTab("log")} className={`tab ${tab === "log" ? "tab-active" : ""}`}><Terminal size={14} /> Falls</button>
            </div>
            {tab === "camera" ? (
              <div className="relative p-3" style={{ minHeight: 280 }}>
                {localCamera ? (
                  <video ref={videoRef} autoPlay playsInline className="h-full w-full object-cover" />
                ) : videoSrc ? (
                  <img src={videoSrc} alt="" className="w-full" onError={() => setFeedError(true)} />
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-3 py-24 text-zinc-500">
                    <Camera size={24} /><span className="text-xs">Backend video stream offline</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="p-4 sm:p-5">
                <div className="mb-5 flex items-center justify-between">
                  <p className="text-sm font-medium">Fall history</p>
                  <span className="micro">{fallCount} events</span>
                </div>
                {activeFalls.length === 0 ? (
                  <div className="rounded-lg border border-line bg-black/20 p-6 text-center">
                    <div className="text-xs text-zinc-500">No falls detected</div>
                  </div>
                ) : (
                  <div className="space-y-0">
                    {[...activeFalls].reverse().map((f, i) => (
                      <div key={i} className="log-row">
                        <span className="log-time">{f.time_str}</span>
                        <div className="min-w-0 flex-1">
                          <div className={`text-sm ${f.outcome === "emergency" ? "text-red-400" : "text-emerald-400"}`}>
                            {f.outcome === "emergency" ? "Emergency alert" : "Fall cancelled"}
                          </div>
                          <div className="micro mt-2">{f.impact_g ? f.impact_g.toFixed(2) + "g" : "—"} · {(f.response_ms / 1000).toFixed(1)}s</div>
                        </div>
                        <span className="event-dot" style={f.outcome === "emergency" ? { background: "#ef4444", boxShadow: "0 0 9px rgba(239,68,68,.5)" } : { background: "#26d887", boxShadow: "0 0 9px rgba(38,216,135,.5)" }} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>

          {/* BOTTOM — Stats spanning full width */}
          <section className="panel p-4 sm:p-5 lg:col-span-2">
            <div className="flex items-center justify-between border-b border-[#242832] pb-3">
              <span className="micro">G-FORCE</span>
              <span className="gforce" style={currentG > 1.5 ? { color: "#ef4444" } : {}}>{currentG.toFixed(2)}<span className="text-2xl">g</span></span>
            </div>
            <div><GForceChart data={gforceHistory.slice(-MAX_G_POINTS)} /></div>

            <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
              <Stat label="PEOPLE" value={String(personCount).padStart(2, "0")} hint="detected" />
              <Stat label="ACTIVITY" value={activityLevel} hint="level" />
              <Stat label="BLE" value={bleLabel} hint={bleConnected ? "Web BLE" : backendOnline ? "server" : "—"} accent={bleConnected || status?.ble_connected} />
              <Stat label="FALLS" value={String(fallCount).padStart(2, "0")} hint="total" accent={fallCount > 0} />
              <Stat label="AVG RESPONSE" value={avgResp} hint="cancelled" />
              <Stat label="ROBOT" value={robotOnline ? "Online" : "Offline"} hint={robotStatus?.mode || "—"} accent={robotOnline} />
            </div>

            <div className="mt-5 grid grid-cols-3 gap-2 sm:grid-cols-6">
              <button className="action-button py-2" onClick={connectBLE}>{bleConnected ? "BLE OK" : "CONNECT BLE"}</button>
              <button className="action-button py-2" onClick={toggleWebcam}>{localCamera ? "STOP CAM" : "LOCAL CAM"}</button>
              <button className="action-button py-2" onClick={() => fetch(API + "/simulate/fall").catch(() => {})}>SIM FALL</button>
              <button className="action-button py-2" onClick={() => fetch(API + "/simulate/emergency").catch(() => {})}>SIM EMERGENCY</button>
              <button className="action-button py-2" onClick={() => fetch(API + "/simulate/reset").catch(() => {})}>RESET</button>
              <button className="action-button py-2" onClick={toggleSeek} disabled={robotLabel.disabled} style={!robotOnline ? { opacity: 0.4 } : {}}>ROBOT</button>
            </div>
          </section>

        </main>

      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
