import React, { useState, useEffect, useCallback } from "react";
import { MODULE_DEFINITIONS, INITIAL_ATTACHED } from "./modulesConfig";

export default function ModulesTab({ backendOnline, apiBase, robotState, onNotification }) {
  const [attached, setAttached] = useState(INITIAL_ATTACHED);
  const [draggedId, setDraggedId] = useState(null);
  const [dragOverSlot, setDragOverSlot] = useState(null);

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
          dragOver={dragOverSlot === "left_arm"}
          onDragOver={e => onDragOver(e, "left_arm")}
          onDragLeave={e => onDragLeave(e, "left_arm")}
          onDrop={e => onDrop(e, "left_arm")}
          onDetach={() => detachModule("left_arm")}
        />
        <ArmSlot
          label="Right Arm" slot="right_arm"
          moduleId={attached.right_arm}
          dragOver={dragOverSlot === "right_arm"}
          onDragOver={e => onDragOver(e, "right_arm")}
          onDragLeave={e => onDragLeave(e, "right_arm")}
          onDrop={e => onDrop(e, "right_arm")}
          onDetach={() => detachModule("right_arm")}
        />
      </div>

      <h2 className="micro">AVAILABLE MODULES</h2>
      <ul className="grid grid-cols-1 gap-2">
        {MODULE_DEFINITIONS.map(mod => {
          const slotLabel = attached.left_arm === mod.id ? "Left" : attached.right_arm === mod.id ? "Right" : null;
          return (
            <li
              key={mod.id}
              draggable
              onDragStart={e => onDragStart(e, mod.id)}
              className={`flex flex-wrap items-center gap-x-3 gap-y-2 border bg-[#0f1117] px-3 py-2.5 cursor-grab active:cursor-grabbing ${
                draggedId === mod.id ? "border-cyan-500/40 opacity-50" : "border-[#242832] hover:border-zinc-600"
              }`}
            >
              <p className="min-w-0 flex-1 text-xs font-medium text-zinc-200">
                {mod.name}
                <small className="micro mt-1 block font-normal text-zinc-500">{mod.description}</small>
              </p>
              {slotLabel ? <span className="micro text-cyan">{slotLabel}</span> : (
                <>
                  {/* Tap-to-attach for touch screens (no drag and drop) */}
                  <button onClick={() => attachModule("left_arm", mod.id)} className="action-button px-3 py-1.5 text-[9px] sm:hidden">LEFT ARM</button>
                  <button onClick={() => attachModule("right_arm", mod.id)} className="action-button px-3 py-1.5 text-[9px] sm:hidden">RIGHT ARM</button>
                </>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ArmSlot({ label, slot, moduleId, dragOver, onDragOver, onDragLeave, onDrop, onDetach }) {
  const mod = moduleId ? MODULE_DEFINITIONS.find(m => m.id === moduleId) : null;

  return (
    <div
      data-drop-slot={slot}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={`border p-3 min-h-[100px] flex flex-col ${
        dragOver
          ? "border-cyan-500/50 bg-cyan-950/20"
          : mod
          ? "border-[#242832] bg-[#0f1117]"
          : "border-dashed border-zinc-700/50 bg-black/20"
      }`}
    >
      <header className="mb-2 flex items-center justify-between">
        <span className="micro font-semibold text-zinc-300">{label.toUpperCase()}</span>
        {mod && <button onClick={onDetach} className="micro text-zinc-500 hover:text-red-400">DETACH</button>}
      </header>
      {mod
        ? <strong className="text-xs font-medium text-zinc-200">{mod.name}</strong>
        : <span className="m-auto text-[10px] text-zinc-500">Drag module here</span>}
    </div>
  );
}
