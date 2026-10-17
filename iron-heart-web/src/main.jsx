import React, { useState, useEffect, useRef, useCallback } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, Camera, ChevronRight, CircleDot, Cpu,
  Heart, Radar, ShieldCheck, Signal, Terminal, Zap, AlertTriangle
} from "lucide-react";
import "./styles.css";

const API = "http://localhost:5001";
const ROBOT = "http://localhost:5002";
const BLE_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214";
const FALL_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214";
const GFORCE_CHAR_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214";
const MAX_G_POINTS = 60;

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

  return (
    <div className="min-h-screen bg-[#090b0f] text-zinc-100">
      <div className="mx-auto min-h-screen max-w-6xl px-3 py-3 sm:px-6 sm:py-6">

        <header className="mb-4 flex items-center justify-between gap-3 px-1 sm:mb-6">
          <div>
            <div className="flex items-center gap-2">
              <div className="brand-mark"><Heart size={16} strokeWidth={2.3} /></div>
              <span className="text-sm font-semibold tracking-[0.22em] sm:text-base">IRON HEART</span>
              <span className="hidden rounded border border-cyan/30 px-2 py-1 font-mono text-[9px] tracking-widest text-cyan sm:inline-flex">SYS.01</span>
            </div>
            <p className="micro mt-2 pl-7">NEURAL INTERFACE / CONTROL SYSTEM</p>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={toggleSeek} disabled={robotLabel.disabled} className={`action-button px-3 py-2 text-[10px] ${!robotOnline ? "opacity-40" : ""}`}>
              <Radar size={13} /> {robotLabel.text}
            </button>
            <button onClick={connectBLE} className={`action-button px-3 py-2 text-[10px] ${bleConnected ? "border-emerald-400/40 text-emerald-300" : bleConnecting ? "border-amber-400/40 text-amber-300" : ""}`}>
              <Signal size={13} /> {bleConnected ? "BLE Connected" : bleConnecting ? "Scanning..." : "Connect BLE"}
            </button>
            <div className="flex items-center gap-2 rounded-lg border border-emerald-400/20 bg-emerald-400/[0.06] px-3 py-2"
              style={banner?.type === "crit" ? { borderColor: "rgba(239,68,68,.3)", background: "rgba(239,68,68,.08)" } : banner?.type === "warn" ? { borderColor: "rgba(245,158,11,.3)", background: "rgba(245,158,11,.08)" } : !backendOnline && !bleConnected ? { borderColor: "rgba(82,82,91,.3)", background: "rgba(82,82,91,.06)" } : {}}>
              <span className="status-dot" style={banner?.type === "crit" ? { background: "#ef4444", boxShadow: "0 0 10px rgba(239,68,68,.5)" } : banner?.type === "warn" ? { background: "#f59e0b", boxShadow: "0 0 10px rgba(245,158,11,.5)" } : !backendOnline && !bleConnected ? { background: "#52525b", boxShadow: "none" } : {}} />
              <span className={`text-[10px] font-semibold tracking-[0.16em] ${banner?.type === "crit" ? "text-red-400" : banner?.type === "warn" ? "text-amber-300" : !backendOnline && !bleConnected ? "text-zinc-500" : "text-emerald-300"}`}>
                {banner?.type === "crit" ? "EMERGENCY" : banner?.type === "warn" ? "FALL DETECTED" : !backendOnline && !bleConnected ? "OFFLINE" : "STABLE"}
              </span>
            </div>
          </div>
        </header>

        {banner && (
          <div className={`mb-4 rounded-lg border px-4 py-3 text-center text-sm font-semibold ${banner.type === "crit" ? "border-red-500/30 bg-red-500/10 text-red-400" : "border-amber-500/30 bg-amber-500/10 text-amber-300"}`}>
            {banner.type === "crit" && <AlertTriangle size={14} className="mr-2 inline" />}
            {banner.text}
          </div>
        )}

        <main className="grid gap-4 lg:grid-cols-[1.15fr_.85fr] lg:gap-5">
          <section className="panel overflow-hidden">
            <div className="flex border-b border-line">
              <button onClick={() => setTab("camera")} className={`tab ${tab === "camera" ? "tab-active" : ""}`}><Camera size={14} /> Camera</button>
              <button onClick={() => setTab("log")} className={`tab ${tab === "log" ? "tab-active" : ""}`}><Terminal size={14} /> Falls</button>
            </div>

            {tab === "camera" ? (
              <div className="p-4 sm:p-5">
                <div className="relative overflow-hidden rounded-lg border border-[#3b414b]" style={{ minHeight: 220 }}>
                  {localCamera ? (
                    <video ref={videoRef} autoPlay playsInline className="w-full" />
                  ) : videoSrc ? (
                    <img src={videoSrc} alt="" className="w-full" onError={() => setFeedError(true)} />
                  ) : (
                    <div className="flex flex-col items-center justify-center gap-3 py-16 text-zinc-500">
                      <Camera size={24} /><span className="text-xs">Backend video stream offline</span>
                    </div>
                  )}
                  {(videoSrc || localCamera) && (
                    <div className="live-pill" style={{ position: "absolute", zIndex: 4, left: 10, top: 10 }}>
                      <span className="live-dot" /> LIVE
                    </div>
                  )}
                </div>

                <div className="mt-4 flex items-center justify-between border-b border-[#242832] pb-3">
                  <span className="micro">G-FORCE</span>
                  <span className="gforce" style={currentG > 1.5 ? { color: "#ef4444" } : {}}>{currentG.toFixed(2)}<span className="text-2xl">g</span></span>
                </div>
                <div className="mt-3"><GForceChart data={gforceHistory.slice(-MAX_G_POINTS)} /></div>

                <div className="mt-4 grid grid-cols-3 gap-3">
                  <Stat label="PEOPLE" value={String(personCount).padStart(2, "0")} hint="detected" />
                  <Stat label="ACTIVITY" value={activityLevel} hint="level" />
                  <Stat label="BLE" value={bleLabel} hint={bleConnected ? "Web BLE" : backendOnline ? "server" : "—"} accent={bleConnected || status?.ble_connected} />
                </div>
                <div className="mt-3 grid grid-cols-3 gap-3">
                  <Stat label="FALLS" value={String(fallCount).padStart(2, "0")} hint="total" accent={fallCount > 0} />
                  <Stat label="AVG RESPONSE" value={avgResp} hint="cancelled" />
                  <Stat label="ROBOT" value={robotOnline ? "Online" : "Offline"} hint={robotStatus?.mode || "—"} accent={robotOnline} />
                </div>

                <div className="mt-5 flex gap-2">
                  <button className="action-button flex-1 py-2" onClick={toggleWebcam}><Camera size={14} /> {localCamera ? "STOP CAM" : "LOCAL CAM"}</button>
                  <button className="action-button flex-1 py-2" onClick={() => fetch(API + "/simulate/fall").catch(() => {})}><Activity size={14} /> SIM FALL</button>
                  <button className="action-button flex-1 py-2" onClick={() => fetch(API + "/simulate/reset").catch(() => {})}><ShieldCheck size={14} /> RESET</button>
                </div>
              </div>
            ) : (
              <div className="p-4 sm:p-5">
                <div className="mb-5 flex items-center justify-between">
                  <div><p className="text-sm font-medium">Fall history</p><p className="micro mt-1">LIVE EVENT STREAM</p></div>
                  <span className="micro">{String(fallCount).padStart(2, "0")} EVENTS</span>
                </div>
                {activeFalls.length === 0 ? (
                  <div className="rounded-lg border border-line bg-black/20 p-6 text-center">
                    <div className="flex items-center justify-center gap-2 text-xs text-zinc-500"><ShieldCheck size={14} className="text-cyan" /> No falls detected</div>
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
                <div className="mt-5 flex gap-2">
                  <button className="action-button flex-1 py-2" onClick={() => fetch(API + "/simulate/fall").catch(() => {})}><Activity size={14} /> SIM FALL</button>
                  <button className="action-button flex-1 py-2" onClick={() => fetch(API + "/simulate/emergency").catch(() => {})}><AlertTriangle size={14} /> SIM EMERGENCY</button>
                  <button className="action-button flex-1 py-2" onClick={() => fetch(API + "/simulate/reset").catch(() => {})}><ShieldCheck size={14} /> RESET</button>
                </div>
              </div>
            )}
          </section>

          <aside className="flex flex-col gap-4">
            <section className="panel p-4 sm:p-5">
              <div className="mb-4 flex items-center justify-between">
                <div><p className="text-sm font-medium">System status</p><p className="micro mt-1">CONNECTION OVERVIEW</p></div>
                <Cpu size={17} className="text-cyan" />
              </div>
              {[
                ["Backend server", backendOnline ? "Online" : "Offline", backendOnline ? 100 : 0],
                ["BLE link", bleLabel, bleConnected ? 100 : status?.ble_connected ? 80 : 0],
                ["Robot bridge", robotOnline ? "Online" : "Offline", robotOnline ? 100 : 0],
                ["Camera feed", localCamera ? "Local" : backendOnline ? "YOLO" : "Offline", localCamera || backendOnline ? 100 : 0],
              ].map(([label, value, pct]) => (
                <div key={label} className="mb-4 last:mb-0">
                  <div className="mb-2 flex justify-between gap-3 text-xs"><span className="text-zinc-400">{label}</span><span className="font-mono text-zinc-200">{value}</span></div>
                  <div className="h-1 overflow-hidden rounded-full bg-zinc-800"><div className={`h-full ${pct > 0 ? "bg-cyan/80" : "bg-zinc-700"}`} style={{ width: `${pct}%` }} /></div>
                </div>
              ))}
            </section>

            <section className="panel p-4 sm:p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-cyan/20 bg-cyan/[0.07]"><Radar size={18} className="text-cyan" /></div>
                <div className="min-w-0 flex-1"><p className="text-sm font-medium">Tracking</p><p className="micro mt-1">{backendOnline ? "YOLO PERSON DETECTION" : "OFFLINE"}</p></div>
                <span className="status-dot" style={!backendOnline ? { background: "#52525b", boxShadow: "none" } : {}} />
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-md border border-line bg-black/20 p-3"><p className="micro">TARGETS</p><p className="mt-2 font-mono text-xl">{String(personCount).padStart(2, "0")}</p></div>
                <div className="rounded-md border border-line bg-black/20 p-3"><p className="micro">G-FORCE</p><p className="mt-2 flex items-center gap-1 font-mono text-xl text-cyan"><Zap size={15} /> {currentG.toFixed(1)}</p></div>
              </div>
            </section>

            <section className="panel p-4 sm:p-5">
              <div className="mb-4 flex items-center justify-between">
                <div><p className="text-sm font-medium">Quick actions</p><p className="micro mt-1">CONTROLS</p></div>
                <Activity size={17} className="text-cyan" />
              </div>
              <div className="flex flex-col gap-2">
                <button className="action-button w-full py-2.5" onClick={connectBLE}>
                  <Signal size={14} /> {bleConnected ? "BLE CONNECTED" : "CONNECT BLE"} <ChevronRight size={14} />
                </button>
                <button className="action-button w-full py-2.5" onClick={toggleSeek} disabled={robotLabel.disabled} style={!robotOnline ? { opacity: 0.4 } : {}}>
                  <Radar size={14} /> {robotLabel.text.toUpperCase()} <ChevronRight size={14} />
                </button>
              </div>
            </section>

            <div className="flex items-center justify-between px-1 py-1">
              <span className="micro flex items-center gap-2"><CircleDot size={11} className="text-cyan" /> {backendOnline || bleConnected ? "SYSTEM ONLINE" : "SYSTEM OFFLINE"}</span>
              <span className="micro">BUILD 01.07.26</span>
            </div>
          </aside>
        </main>

        <footer className="mt-5 flex flex-wrap items-center justify-between gap-2 border-t border-line/70 px-1 pt-4">
          <span className="micro">IRON HEART INTERFACE © 2026</span>
          <span className="micro flex items-center gap-2"><Zap size={11} className="text-cyan" /> DESIGNED FOR THE NEXT GENERATION</span>
        </footer>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
