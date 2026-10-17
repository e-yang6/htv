import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, BatteryFull, Camera, ChevronRight, CircleDot, Cpu,
  Heart, Radar, ShieldCheck, Signal, Terminal, Zap
} from "lucide-react";
import "./styles.css";

const logs = [
  { time: "14:32:06", title: "Target acquired", detail: "Person 01 / confidence 98.6%", active: true },
  { time: "14:31:42", title: "Core synchronized", detail: "Neural link latency / 12 ms" },
  { time: "14:30:18", title: "Diagnostics passed", detail: "All core parameters nominal" },
  { time: "14:30:18", title: "Diagnostics passed", detail: "All core parameters nominal" },
  { time: "14:30:18", title: "Diagnostics passed", detail: "All core parameters nominal" },
];

function Stat({ label, value, hint, accent = false }) {
  return <div className="min-w-0">
    <div className="micro mb-2">{label}</div>
    <div className={`stat-value ${accent ? "text-cyan" : ""}`}>{value}</div>
    <div className="micro mt-2 text-zinc-600">{hint}</div>
  </div>;
}

function App() {
  const [tab, setTab] = useState("camera");
  const [bpm, setBpm] = useState(72);
  const [simulated, setSimulated] = useState(false);

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
          <div className="flex items-center gap-2 rounded-lg border border-emerald-400/20 bg-emerald-400/[0.06] px-3 py-2">
            <span className="status-dot" />
            <span className="text-[10px] font-semibold tracking-[0.16em] text-emerald-300">STABLE</span>
          </div>
        </header>

        <main className="grid gap-4 lg:grid-cols-[1.15fr_.85fr] lg:gap-5">
          <section className="panel overflow-hidden">
            <div className="flex border-b border-line">
              <button onClick={() => setTab("camera")} className={`tab ${tab === "camera" ? "tab-active" : ""}`}>
                <Camera size={14} /> Camera View
              </button>
              <button onClick={() => setTab("log")} className={`tab ${tab === "log" ? "tab-active" : ""}`}>
                <Terminal size={14} /> Session Log
              </button>
            </div>

            {tab === "camera" ? (
              <div className="p-4 sm:p-5">
                <div className="mb-1 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-medium"><Heart size={17} className="text-cyan" /> CORE HEART</div>
                  <span className="rounded-md border border-cyan/20 bg-cyan/[0.08] px-2.5 py-1.5 font-mono text-[10px] text-cyan">● ACTIVE</span>
                </div>

                <div className="heart-stage">
                  <div className="heart-aura" />
                  <img src="/heart.png" alt="Glossy electric-blue heart" className="heart-art" />
                  <div className="orbit orbit-one" />
                  <div className="orbit orbit-two" />
                </div>
                <div className="beat-readout">
                  <span className="micro">PULSE FREQUENCY</span>
                  <span className="font-mono text-xs text-cyan">{bpm} <span className="text-zinc-500">BPM</span></span>
                </div>

                <div className="camera-frame">
                  <div className="camera-grid" />
                  <div className="live-pill"><span className="live-dot" /> LIVE SIMULATION</div>
                  <div className="face-tag">PERSON 01 · 98.6%</div>
                  <div className="tracking-box">
                    <span className="corner corner-tl" /><span className="corner corner-tr" />
                    <span className="corner corner-bl" /><span className="corner corner-br" />
                    <span className="crosshair">+</span>
                  </div>
                  <div className="scanline" />
                  <div className="camera-bottom"><span>1920 × 1080 / 30 FPS</span><span>FRONT CAMERA</span></div>
                </div>
                <p className="micro mt-2 text-center">DEMO FEED — CAMERA ACCESS NOT CONNECTED</p>

                <div className="mt-5 flex items-end justify-between border-b border-line pb-4">
                  <span className="micro">G-FORCE</span>
                  <span className="gforce">1.00<span className="text-2xl">g</span></span>
                </div>
                <div className="grid grid-cols-3 gap-3 pt-4">
                  <Stat label="OBJECTS" value="01" hint="person detected" />
                  <Stat label="CONFIDENCE" value="98.6%" hint="simulation" />
                  <Stat label="CORE TEMP" value="36.8°" hint="nominal" accent />
                </div>
                <button className="action-button mt-5 w-full" onClick={() => {
                  setSimulated(!simulated);
                  setBpm(simulated ? 72 : 96);
                }}>
                  <Activity size={14} /> {simulated ? "RESET HEART RATE" : "SIMULATE ELEVATED PULSE"} <ChevronRight size={14} />
                </button>
              </div>
            ) : (
              <div className="p-4 sm:p-5">
                <div className="mb-5 flex items-center justify-between">
                  <div><p className="text-sm font-medium">System activity</p><p className="micro mt-1">LIVE EVENT STREAM</p></div>
                  <span className="micro">05 EVENTS</span>
                </div>
                <div className="space-y-0">
                  {logs.map((item, i) => <div key={i} className="log-row">
                    <span className="log-time">{item.time}</span>
                    <div className="min-w-0 flex-1">
                      <div className={`text-sm ${item.active ? "text-cyan" : "text-zinc-200"}`}>{item.title}</div>
                      <div className="micro mt-2 truncate">{item.detail}</div>
                    </div>
                    <span className={`event-dot ${item.active ? "event-dot-active" : ""}`} />
                  </div>)}
                </div>
                <div className="mt-5 rounded-lg border border-line bg-black/20 p-3">
                  <div className="flex items-center gap-2 text-xs text-zinc-400"><ShieldCheck size={14} className="text-cyan" /> All core parameters nominal</div>
                </div>
              </div>
            )}
          </section>

          <aside className="flex flex-col gap-4">
            <section className="panel p-4 sm:p-5">
              <div className="mb-5 flex items-start justify-between">
                <div><p className="text-sm font-medium">Energy reserve</p><p className="micro mt-1">POWER MANAGEMENT</p></div>
                <BatteryFull size={18} className="text-zinc-400" />
              </div>
              <div className="flex items-end justify-between">
                <div className="text-5xl font-light tracking-tight">67<span className="ml-1 text-lg text-zinc-500">%</span></div>
                <span className="mb-2 font-mono text-[10px] tracking-widest text-cyan">ON BATTERY</span>
              </div>
              <div className="mt-5 grid grid-cols-18 gap-1" style={{gridTemplateColumns:"repeat(18,minmax(0,1fr))"}}>
                {Array.from({length:18},(_,i)=><span key={i} className={`h-5 ${i<12?"bg-cyan/60":"bg-zinc-800"}`} />)}
              </div>
              <div className="mt-6 flex justify-between gap-3">
                <div><p className="micro">EST. REMAINING</p><p className="mt-2 font-mono text-sm">05 h 12 m</p></div>
                <div className="text-right"><p className="micro">VOLTAGE</p><p className="mt-2 font-mono text-sm">48.0 V</p></div>
              </div>
            </section>

            <section className="panel p-4 sm:p-5">
              <div className="mb-4 flex items-center justify-between">
                <div><p className="text-sm font-medium">Core diagnostics</p><p className="micro mt-1">SYSTEM HEALTH</p></div>
                <Cpu size={17} className="text-cyan" />
              </div>
              {[
                ["Neural link", "12 ms", 82],
                ["Signal integrity", "99.2%", 99],
                ["Core stability", "OPTIMAL", 94],
              ].map(([label, value, pct]) => <div key={label} className="mb-4 last:mb-0">
                <div className="mb-2 flex justify-between gap-3 text-xs"><span className="text-zinc-400">{label}</span><span className="font-mono text-zinc-200">{value}</span></div>
                <div className="h-1 overflow-hidden rounded-full bg-zinc-800"><div className="h-full bg-cyan/80" style={{width:`${pct}%`}} /></div>
              </div>)}
            </section>

            <section className="panel p-4 sm:p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-cyan/20 bg-cyan/[0.07]"><Radar size={18} className="text-cyan" /></div>
                <div className="min-w-0 flex-1"><p className="text-sm font-medium">Tracking system</p><p className="micro mt-1">SIMULATION MODE</p></div>
                <span className="status-dot" />
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-md border border-line bg-black/20 p-3"><p className="micro">TARGETS</p><p className="mt-2 font-mono text-xl">01</p></div>
                <div className="rounded-md border border-line bg-black/20 p-3"><p className="micro">SIGNAL</p><p className="mt-2 flex items-center gap-1 font-mono text-xl text-cyan"><Signal size={15}/> 98%</p></div>
              </div>
            </section>
            <div className="flex items-center justify-between px-1 py-1">
              <span className="micro flex items-center gap-2"><CircleDot size={11} className="text-cyan" /> SYSTEM ONLINE</span>
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
