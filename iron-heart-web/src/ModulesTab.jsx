import React, { useState, useEffect, useCallback } from "react";
import { MODULE_DEFINITIONS, INITIAL_ATTACHED } from "./modulesConfig";

export default function ModulesTab({ backendOnline, apiBase, robotState, onNotification }) {
  const [attached, setAttached] = useState(INITIAL_ATTACHED);
  const [draggedId, setDraggedId] = useState(null);
  const [dragOverSlot, setDragOverSlot] = useState(null);
  const [customModules, setCustomModules] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("ironheart_custom_modules") || "[]");
    } catch { return []; }
  });
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  const allModules = [...MODULE_DEFINITIONS, ...customModules];

  const saveCustom = (mods) => {
    setCustomModules(mods);
    try { localStorage.setItem("ironheart_custom_modules", JSON.stringify(mods)); } catch {}
  };

  const addCustomModule = () => {
    const name = newName.trim();
    if (!name) return;
    const id = "custom_" + Date.now();
    saveCustom([...customModules, { id, name, description: newDesc.trim() || "Custom module", supportedSlots: ["left_arm", "right_arm"], actions: [] }]);
    setNewName("");
    setNewDesc("");
    setShowAdd(false);
  };

  const removeCustomModule = (id) => {
    setAttached(prev => {
      const next = { ...prev };
      if (next.left_arm === id) next.left_arm = null;
      if (next.right_arm === id) next.right_arm = null;
      return next;
    });
    saveCustom(customModules.filter(m => m.id !== id));
  };

  useEffect(() => {
    if (!backendOnline) return;
    let alive = true;
    fetch(`${apiBase}/modules/attached`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!alive || !data) return;
        setAttached(prev => ({
          left_arm: data.left_arm ? data.left_arm.id : prev.left_arm,
          right_arm: data.right_arm ? data.right_arm.id : prev.right_arm,
        }));
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [backendOnline, apiBase]);

  const attachModule = useCallback(async (slot, moduleId) => {
    setAttached(prev => {
      const next = { ...prev };
      const other = slot === "left_arm" ? "right_arm" : "left_arm";
      if (next[other] === moduleId) next[other] = null;
      next[slot] = moduleId;
      return next;
    });
    if (backendOnline) {
      try {
        await fetch(`${apiBase}/modules/attach`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slot, module_id: moduleId }),
        });
      } catch {}
    }
  }, [backendOnline, apiBase]);

  const detachModule = useCallback(async (slot) => {
    setAttached(prev => ({ ...prev, [slot]: null }));
    if (backendOnline) {
      try {
        await fetch(`${apiBase}/modules/detach`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slot }),
        });
      } catch {}
    }
  }, [backendOnline, apiBase]);

  const onDragStart = (e, id) => {
    e.dataTransfer.setData("text/plain", id);
    setDraggedId(id);
  };
  const onDragOver = (e, slot) => { e.preventDefault(); setDragOverSlot(slot); };
  const onDragLeave = (e, slot) => { e.preventDefault(); if (dragOverSlot === slot) setDragOverSlot(null); };
  const onDrop = (e, slot) => {
    e.preventDefault();
    const id = e.dataTransfer.getData("text/plain") || draggedId;
    if (id) attachModule(slot, id);
    setDraggedId(null);
    setDragOverSlot(null);
  };

  return (
    <div className="flex flex-col gap-3 p-3 sm:p-5">
      {/* Arm slots */}
      <div className="grid grid-cols-2 gap-2 sm:gap-3">
        <ArmSlot
          label="Left Arm" slot="left_arm"
          moduleId={attached.left_arm}
          allModules={allModules}
          dragOver={dragOverSlot === "left_arm"}
          onDragOver={e => onDragOver(e, "left_arm")}
          onDragLeave={e => onDragLeave(e, "left_arm")}
          onDrop={e => onDrop(e, "left_arm")}
          onDetach={() => detachModule("left_arm")}
        />
        <ArmSlot
          label="Right Arm" slot="right_arm"
          moduleId={attached.right_arm}
          allModules={allModules}
          dragOver={dragOverSlot === "right_arm"}
          onDragOver={e => onDragOver(e, "right_arm")}
          onDragLeave={e => onDragLeave(e, "right_arm")}
          onDrop={e => onDrop(e, "right_arm")}
          onDetach={() => detachModule("right_arm")}
        />
      </div>

      {/* Module tray */}
      <div>
        <div className="flex items-center justify-between">
          <span className="micro">AVAILABLE MODULES</span>
          <button onClick={() => setShowAdd(!showAdd)} className="micro text-cyan hover:text-white transition-colors">
            {showAdd ? "CANCEL" : "+ ADD"}
          </button>
        </div>

        {showAdd && (
          <div className="mt-2 rounded-lg border border-[#242832] bg-[#0f1117] p-3">
            <input
              type="text"
              placeholder="Module name"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              className="w-full bg-transparent text-xs text-zinc-200 outline-none border-b border-zinc-700 pb-2 mb-2"
              autoFocus
            />
            <input
              type="text"
              placeholder="Description (optional)"
              value={newDesc}
              onChange={e => setNewDesc(e.target.value)}
              className="w-full bg-transparent text-xs text-zinc-400 outline-none border-b border-zinc-700 pb-2 mb-3"
            />
            <button
              onClick={addCustomModule}
              disabled={!newName.trim()}
              className="action-button w-full py-1.5 text-[10px]"
              style={!newName.trim() ? { opacity: 0.4 } : {}}
            >
              ADD MODULE
            </button>
          </div>
        )}

        <div className="mt-2 grid grid-cols-1 gap-2">
          {allModules.map(mod => {
            const onLeft = attached.left_arm === mod.id;
            const onRight = attached.right_arm === mod.id;
            const slotLabel = onLeft ? "Left" : onRight ? "Right" : null;
            const isCustom = mod.id.startsWith("custom_");
            return (
              <div
                key={mod.id}
                draggable
                onDragStart={e => onDragStart(e, mod.id)}
                className={`rounded-lg border bg-[#0f1117] px-3 py-2.5 cursor-grab active:cursor-grabbing transition-all ${
                  draggedId === mod.id ? "border-cyan-500/40 opacity-50" : "border-[#242832] hover:border-zinc-600"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-zinc-200">{mod.name}</div>
                    <div className="micro mt-1 text-zinc-500">{mod.description}</div>
                  </div>
                  <div className="flex items-center gap-2 ml-2 shrink-0">
                    {slotLabel && <span className="micro text-cyan">{slotLabel}</span>}
                    {isCustom && (
                      <button onClick={() => removeCustomModule(mod.id)} className="micro text-zinc-600 hover:text-red-400 transition-colors">✕</button>
                    )}
                  </div>
                </div>
                {/* Tap-to-attach buttons for mobile */}
                {!slotLabel && (
                  <div className="mt-2 grid grid-cols-2 gap-2 sm:hidden">
                    <button onClick={() => attachModule("left_arm", mod.id)} className="action-button py-1.5 text-[9px]">LEFT ARM</button>
                    <button onClick={() => attachModule("right_arm", mod.id)} className="action-button py-1.5 text-[9px]">RIGHT ARM</button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ArmSlot({ label, slot, moduleId, allModules, dragOver, onDragOver, onDragLeave, onDrop, onDetach }) {
  const mod = moduleId ? allModules.find(m => m.id === moduleId) : null;

  return (
    <div
      data-drop-slot={slot}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={`rounded-lg border p-3 transition-all min-h-[100px] flex flex-col ${
        dragOver
          ? "border-cyan-500/50 bg-cyan-950/20"
          : mod
          ? "border-[#242832] bg-[#0f1117]"
          : "border-dashed border-zinc-700/50 bg-black/20"
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="micro font-semibold text-zinc-300">{label.toUpperCase()}</span>
        {mod && (
          <button onClick={onDetach} className="micro text-zinc-500 hover:text-red-400 transition-colors">DETACH</button>
        )}
      </div>

      {mod ? (
        <div className="flex-1 flex items-center">
          <div className="text-xs font-medium text-zinc-200">{mod.name}</div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-[10px] text-zinc-500">Drag module here</span>
        </div>
      )}
    </div>
  );
}
