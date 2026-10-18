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

  const slotProps = (slot) => ({
    slot, moduleId: attached[slot], dragOver: dragOverSlot === slot,
    onDragOver: e => onDragOver(e, slot), onDragLeave: e => onDragLeave(e, slot),
    onDrop: e => onDrop(e, slot), onDetach: () => detachModule(slot),
  });

  return (
    <>
      <div className="slots">
        <ArmSlot label="Left arm" {...slotProps("left_arm")} />
        <ArmSlot label="Right arm" {...slotProps("right_arm")} />
      </div>

      <h2>Available modules</h2>
      <ul className="modules">
        {MODULE_DEFINITIONS.map(mod => {
          const slotLabel = attached.left_arm === mod.id ? "On left arm" : attached.right_arm === mod.id ? "On right arm" : null;
          return (
            <li key={mod.id} draggable onDragStart={e => onDragStart(e, mod.id)}
                className={draggedId === mod.id ? "dragging" : undefined}>
              <div>
                <strong>{mod.name}</strong>
                <p>{mod.description}</p>
              </div>
              {slotLabel ? <span className="muted">{slotLabel}</span> : (
                <>
                  <button onClick={() => attachModule("left_arm", mod.id)} className="btn">Left</button>
                  <button onClick={() => attachModule("right_arm", mod.id)} className="btn">Right</button>
                </>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

function ArmSlot({ label, slot, moduleId, dragOver, onDragOver, onDragLeave, onDrop, onDetach }) {
  const mod = moduleId ? MODULE_DEFINITIONS.find(m => m.id === moduleId) : null;
  return (
    <div data-drop-slot={slot} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
         className={`slot ${mod ? "filled" : ""} ${dragOver ? "over" : ""}`}>
      <header>
        <span>{label}</span>
        {mod && <button onClick={onDetach} className="link">Detach</button>}
      </header>
      {mod ? <strong>{mod.name}</strong> : <span className="muted">Drag a module here</span>}
    </div>
  );
}
