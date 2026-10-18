import React, { useState, useEffect, useCallback } from "react";
import { MODULE_DEFINITIONS, INITIAL_ATTACHED } from "./modulesConfig";

export default function ModulesTab({ backendOnline, apiBase, robotState, onNotification }) {
  const [attached, setAttached] = useState(INITIAL_ATTACHED);
  const [isExecuting, setIsExecuting] = useState({});
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

  const executeAction = useCallback(async (slot, actionId) => {
    const moduleId = attached[slot];
    if (!moduleId) return;
    const mod = MODULE_DEFINITIONS.find(m => m.id === moduleId);
    if (!mod) return;
    const action = mod.actions.find(a => a.id === actionId);
    setIsExecuting(prev => ({ ...prev, [slot]: true }));
    try {
      if (backendOnline) {
        try {
          await fetch(`${apiBase}/modules/execute`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slot, action: actionId }),
          });
        } catch {}
      }
      if (action?.handler) await action.handler({ slot, robotState, params: null });
    } catch {} finally {
      setTimeout(() => setIsExecuting(prev => ({ ...prev, [slot]: false })), 300);
    }
  }, [attached, backendOnline, apiBase, robotState]);

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
    <div className="flex flex-col gap-4 p-4 sm:p-5">
      {/* Arm slots */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <ArmSlot
          label="Left Arm" slot="left_arm"
          moduleId={attached.left_arm}
          executing={isExecuting.left_arm}
          dragOver={dragOverSlot === "left_arm"}
          onDragOver={e => onDragOver(e, "left_arm")}
          onDragLeave={e => onDragLeave(e, "left_arm")}
          onDrop={e => onDrop(e, "left_arm")}
          onDetach={() => detachModule("left_arm")}
          onExecute={id => executeAction("left_arm", id)}
        />
        <ArmSlot
          label="Right Arm" slot="right_arm"
          moduleId={attached.right_arm}
          executing={isExecuting.right_arm}
          dragOver={dragOverSlot === "right_arm"}
          onDragOver={e => onDragOver(e, "right_arm")}
          onDragLeave={e => onDragLeave(e, "right_arm")}
          onDrop={e => onDrop(e, "right_arm")}
          onDetach={() => detachModule("right_arm")}
          onExecute={id => executeAction("right_arm", id)}
        />
      </div>

      {/* Module tray */}
      <div>
        <span className="micro">AVAILABLE MODULES</span>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {MODULE_DEFINITIONS.map(mod => {
            const slot = attached.left_arm === mod.id ? "Left" : attached.right_arm === mod.id ? "Right" : null;
            return (
              <div
                key={mod.id}
                draggable
                onDragStart={e => onDragStart(e, mod.id)}
                className={`flex items-center justify-between rounded-lg border bg-[#0f1117] px-3 py-2.5 cursor-grab active:cursor-grabbing transition-all ${
                  draggedId === mod.id ? "border-cyan-500/40 opacity-50" : "border-[#242832] hover:border-zinc-600"
                }`}
              >
                <div className="min-w-0">
                  <div className="text-xs font-medium text-zinc-200">{mod.name}</div>
                  <div className="micro mt-1 text-zinc-500">{mod.description}</div>
                </div>
                {slot && <span className="ml-2 shrink-0 micro text-cyan">{slot}</span>}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ArmSlot({ label, slot, moduleId, executing, dragOver, onDragOver, onDragLeave, onDrop, onDetach, onExecute }) {
  const mod = moduleId ? MODULE_DEFINITIONS.find(m => m.id === moduleId) : null;

  return (
    <div
      data-drop-slot={slot}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={`rounded-lg border p-3.5 transition-all min-h-[140px] flex flex-col ${
        dragOver
          ? "border-cyan-500/50 bg-cyan-950/20"
          : mod
          ? "border-[#242832] bg-[#0f1117]"
          : "border-dashed border-zinc-700/50 bg-black/20"
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="micro font-semibold text-zinc-300">{label.toUpperCase()}</span>
        {mod && (
          <button onClick={onDetach} className="micro text-zinc-500 hover:text-red-400 transition-colors">DETACH</button>
        )}
      </div>

      {mod ? (
        <div className="flex-1 flex items-center">
          <div className="text-sm font-medium text-zinc-200">{mod.name}</div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-xs text-zinc-500">Drag a module here</span>
        </div>
      )}
    </div>
  );
}
