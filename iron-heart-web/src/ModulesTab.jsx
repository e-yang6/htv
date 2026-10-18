import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  Syringe,
  Pill,
  Bot,
  Trash2,
  Play,
  RotateCcw,
  Check,
  Layers
} from "lucide-react";
import { MODULE_DEFINITIONS, INITIAL_ATTACHED } from "./modulesConfig";

const ICONS = {
  Syringe,
  Pill,
};

export default function ModulesTab({
  backendOnline,
  apiBase,
  robotState,
  onNotification,
}) {
  const [attached, setAttached] = useState(INITIAL_ATTACHED);
  const [draggedModuleId, setDraggedModuleId] = useState(null);
  const [dragOverSlot, setDragOverSlot] = useState(null);
  const [isExecuting, setIsExecuting] = useState({});

  // Touch drag state
  const touchGhostRef = useRef(null);
  const [touchDragging, setTouchDragging] = useState(null);

  // Sync with backend if available
  useEffect(() => {
    if (!backendOnline) return;
    let isMounted = true;
    fetch(`${apiBase}/modules/attached`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!isMounted || !data) return;
        setAttached((prev) => ({
          left_arm: data.left_arm ? data.left_arm.id : prev.left_arm,
          right_arm: data.right_arm ? data.right_arm.id : prev.right_arm,
        }));
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, [backendOnline, apiBase]);

  // Attach module to a slot
  const attachModule = useCallback(
    async (slot, moduleId) => {
      const moduleDef = MODULE_DEFINITIONS.find((m) => m.id === moduleId);
      if (!moduleDef) return;

      setAttached((prev) => {
        const next = { ...prev };
        const otherSlot = slot === "left_arm" ? "right_arm" : "left_arm";
        if (next[otherSlot] === moduleId) {
          next[otherSlot] = null;
        }
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
        } catch (err) {
          console.warn("Backend attach sync error:", err);
        }
      }
    },
    [backendOnline, apiBase]
  );

  // Detach module from a slot
  const detachModule = useCallback(
    async (slot) => {
      const currentId = attached[slot];
      if (!currentId) return;

      setAttached((prev) => ({ ...prev, [slot]: null }));

      if (backendOnline) {
        try {
          await fetch(`${apiBase}/modules/detach`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slot }),
          });
        } catch (err) {
          console.warn("Backend detach sync error:", err);
        }
      }
    },
    [attached, backendOnline, apiBase]
  );

  // Execute module function
  const executeAction = useCallback(
    async (slot, actionId) => {
      const moduleId = attached[slot];
      if (!moduleId) return;

      const moduleDef = MODULE_DEFINITIONS.find((m) => m.id === moduleId);
      if (!moduleDef) return;

      const actionDef = moduleDef.actions.find((a) => a.id === actionId);
      setIsExecuting((prev) => ({ ...prev, [slot]: true }));

      try {
        let result = null;
        if (backendOnline) {
          try {
            const resp = await fetch(`${apiBase}/modules/execute`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ slot, action: actionId }),
            });
            if (resp.ok) {
              const data = await resp.json();
              result = data.exec_result;
            }
          } catch (e) {
            console.warn("Backend call failed, using local handler:", e);
          }
        }

        if (!result && actionDef && actionDef.handler) {
          await actionDef.handler({
            slot,
            robotState,
            params: null,
          });
        }
      } catch (err) {
        console.error("Failed to execute module action:", err);
      } finally {
        setTimeout(() => {
          setIsExecuting((prev) => ({ ...prev, [slot]: false }));
        }, 300);
      }
    },
    [attached, backendOnline, apiBase, robotState]
  );

  // Desktop Drag & Drop Handlers
  const handleDragStart = (e, moduleId) => {
    e.dataTransfer.setData("text/plain", moduleId);
    e.dataTransfer.effectAllowed = "copyMove";
    setDraggedModuleId(moduleId);
  };

  const handleDragOver = (e, slot) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOverSlot !== slot) {
      setDragOverSlot(slot);
    }
  };

  const handleDragLeave = (e, slot) => {
    e.preventDefault();
    if (dragOverSlot === slot) {
      setDragOverSlot(null);
    }
  };

  const handleDrop = (e, slot) => {
    e.preventDefault();
    setDragOverSlot(null);
    setDraggedModuleId(null);
    const moduleId = e.dataTransfer.getData("text/plain") || draggedModuleId;
    if (moduleId && (slot === "left_arm" || slot === "right_arm")) {
      attachModule(slot, moduleId);
    }
  };

  // Mobile Touch Drag Handlers
  const handleTouchStart = (e, moduleId) => {
    const touch = e.touches[0];
    setTouchDragging(moduleId);

    if (touchGhostRef.current) {
      touchGhostRef.current.style.left = `${touch.clientX}px`;
      touchGhostRef.current.style.top = `${touch.clientY}px`;
      touchGhostRef.current.style.display = "flex";
    }
  };

  const handleTouchMove = (e) => {
    if (!touchDragging) return;
    const touch = e.touches[0];
    if (touchGhostRef.current) {
      touchGhostRef.current.style.left = `${touch.clientX}px`;
      touchGhostRef.current.style.top = `${touch.clientY}px`;
    }

    const elem = document.elementFromPoint(touch.clientX, touch.clientY);
    const dropZone = elem?.closest("[data-drop-slot]");
    if (dropZone) {
      const slot = dropZone.getAttribute("data-drop-slot");
      setDragOverSlot(slot);
    } else {
      setDragOverSlot(null);
    }
  };

  const handleTouchEnd = (e) => {
    if (!touchDragging) return;
    if (touchGhostRef.current) {
      touchGhostRef.current.style.display = "none";
    }

    const elem = document.elementFromPoint(touch.clientX, touch.clientY);
    const dropZone = elem?.closest("[data-drop-slot]");
    if (dropZone) {
      const slot = dropZone.getAttribute("data-drop-slot");
      if (slot === "left_arm" || slot === "right_arm") {
        attachModule(slot, touchDragging);
      }
    }
    setTouchDragging(null);
    setDragOverSlot(null);
  };

  return (
    <div className="flex flex-col gap-4 p-3 sm:p-5">
      {/* Floating Ghost for Touch Dragging */}
      <div
        ref={touchGhostRef}
        className="pointer-events-none fixed z-50 -translate-x-1/2 -translate-y-1/2 rounded-lg border border-cyan-400 bg-zinc-900/95 px-3 py-2 text-xs font-semibold text-cyan shadow-xl backdrop-blur"
        style={{ display: "none" }}
      >
        <span>Dragging: {touchDragging}</span>
      </div>

      {/* Top Bar with System Status & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan">
            <Bot size={16} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold tracking-wider uppercase text-zinc-200">
                Robot Dual-Arm Modularity
              </span>
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] font-mono uppercase ${
                  backendOnline
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                    : "bg-cyan-500/10 text-cyan border border-cyan-500/30"
                }`}
              >
                {backendOnline ? "Live Sync" : "Decoupled Mode"}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={() => {
              detachModule("left_arm");
              detachModule("right_arm");
            }}
            className="action-button px-2.5 py-1 text-[11px] hover:text-red-400 hover:border-red-500/50"
            title="Clear all attached modules"
          >
            <RotateCcw size={13} />
            <span className="hidden sm:inline">Clear</span>
          </button>
        </div>
      </div>

      {/* ROBOT DUAL ARM SCHEMATIC / DROP ZONES */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {/* LEFT ARM */}
        <ArmSlotCard
          slot="left_arm"
          label="Left Arm"
          moduleId={attached.left_arm}
          dragOver={dragOverSlot === "left_arm"}
          isExecuting={isExecuting.left_arm}
          onDragOver={(e) => handleDragOver(e, "left_arm")}
          onDragLeave={(e) => handleDragLeave(e, "left_arm")}
          onDrop={(e) => handleDrop(e, "left_arm")}
          onDetach={() => detachModule("left_arm")}
          onExecuteAction={(actionId) => executeAction("left_arm", actionId)}
        />

        {/* RIGHT ARM */}
        <ArmSlotCard
          slot="right_arm"
          label="Right Arm"
          moduleId={attached.right_arm}
          dragOver={dragOverSlot === "right_arm"}
          isExecuting={isExecuting.right_arm}
          onDragOver={(e) => handleDragOver(e, "right_arm")}
          onDragLeave={(e) => handleDragLeave(e, "right_arm")}
          onDrop={(e) => handleDrop(e, "right_arm")}
          onDetach={() => detachModule("right_arm")}
          onExecuteAction={(actionId) => executeAction("right_arm", actionId)}
        />
      </div>

      {/* AVAILABLE MODULES TRAY */}
      <div className="rounded-xl border border-line bg-black/30 p-3 sm:p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers size={14} className="text-cyan" />
            <span className="micro uppercase font-semibold text-zinc-300">
              Available Modules
            </span>
          </div>
          <span className="micro text-zinc-500">
            {MODULE_DEFINITIONS.length} Modules Available
          </span>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {MODULE_DEFINITIONS.map((mod) => {
            const Icon = ICONS[mod.iconName] || Bot;
            const isLeftAttached = attached.left_arm === mod.id;
            const isRightAttached = attached.right_arm === mod.id;

            return (
              <div
                key={mod.id}
                draggable
                onDragStart={(e) => handleDragStart(e, mod.id)}
                onTouchStart={(e) => handleTouchStart(e, mod.id)}
                onTouchMove={handleTouchMove}
                onTouchEnd={handleTouchEnd}
                className="group relative flex flex-col justify-between rounded-xl border border-line bg-zinc-900/60 hover:border-zinc-700 hover:bg-zinc-900/90 p-3.5 transition-all cursor-grab active:cursor-grabbing"
                style={{
                  borderLeftColor: mod.color,
                  borderLeftWidth: "4px",
                }}
              >
                {/* Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div
                      className="flex h-9 w-9 items-center justify-center rounded-lg"
                      style={{
                        backgroundColor: mod.accentBg,
                        color: mod.color,
                        boxShadow: `0 0 12px ${mod.glowColor}`,
                      }}
                    >
                      <Icon size={18} />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-zinc-100 group-hover:text-cyan transition-colors">
                        {mod.name}
                      </div>
                    </div>
                  </div>

                  {/* Active Status Badge */}
                  <div className="text-right">
                    {isLeftAttached || isRightAttached ? (
                      <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-mono text-emerald-400 border border-emerald-500/20">
                        <Check size={10} />
                        {isLeftAttached && isRightAttached
                          ? "Both Arms"
                          : isLeftAttached
                          ? "Left Arm"
                          : "Right Arm"}
                      </span>
                    ) : (
                      <span className="rounded bg-zinc-800/80 px-1.5 py-0.5 text-[9px] font-mono text-zinc-400">
                        Ready
                      </span>
                    )}
                  </div>
                </div>

                {/* Description */}
                <p className="mt-2.5 text-[11px] leading-relaxed text-zinc-400">
                  {mod.description}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// Arm Slot Component
function ArmSlotCard({
  slot,
  label,
  moduleId,
  dragOver,
  isExecuting,
  onDragOver,
  onDragLeave,
  onDrop,
  onDetach,
  onExecuteAction,
}) {
  const moduleDef = moduleId
    ? MODULE_DEFINITIONS.find((m) => m.id === moduleId)
    : null;
  const Icon = moduleDef ? ICONS[moduleDef.iconName] || Bot : null;

  return (
    <div
      data-drop-slot={slot}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={`relative flex flex-col justify-between rounded-xl border p-3.5 sm:p-4 transition-all min-h-[175px] ${
        dragOver
          ? "border-cyan-400 bg-cyan-950/40 shadow-[0_0_20px_rgba(24,191,244,0.3)] ring-2 ring-cyan-400"
          : moduleId
          ? "border-[#282d36] bg-gradient-to-b from-zinc-900/90 to-zinc-950/90"
          : "border-dashed border-zinc-700/60 bg-black/20 hover:border-zinc-500"
      }`}
    >
      {/* Slot Header */}
      <div className="flex items-center justify-between border-b border-line pb-2.5">
        <div className="flex items-center gap-2">
          <div
            className={`h-2.5 w-2.5 rounded-full ${
              moduleId
                ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]"
                : "bg-zinc-600"
            }`}
          />
          <div className="text-xs font-semibold text-zinc-100 uppercase tracking-wider">
            {label}
          </div>
        </div>

        {moduleId ? (
          <button
            onClick={onDetach}
            className="action-button px-2 py-1 text-[10px] hover:text-red-400 hover:border-red-500/40"
            title="Detach module"
          >
            <Trash2 size={11} />
          </button>
        ) : (
          <span className="micro text-zinc-500 font-mono">EMPTY</span>
        )}
      </div>

      {/* Center Slot Content */}
      {moduleDef ? (
        <div className="my-3 flex flex-col gap-2.5">
          <div className="flex items-center gap-3">
            <div
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl"
              style={{
                backgroundColor: moduleDef.accentBg,
                color: moduleDef.color,
                boxShadow: `0 0 16px ${moduleDef.glowColor}`,
                border: `1px solid ${moduleDef.borderColor}`,
              }}
            >
              <Icon size={22} />
            </div>

            <div className="min-w-0 flex-1">
              <div className="text-xs font-bold text-zinc-100 truncate">
                {moduleDef.name}
              </div>
            </div>
          </div>

          {/* Action Trigger Button */}
          <div className="mt-1 space-y-1.5">
            {moduleDef.actions.map((act) => (
              <button
                key={act.id}
                disabled={isExecuting}
                onClick={() => onExecuteAction(act.id)}
                className="flex w-full items-center justify-between rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan hover:bg-cyan-500/20 active:scale-[0.98] transition-all"
              >
                <span className="flex items-center gap-1.5">
                  <Play size={12} className="text-cyan" />
                  {act.label}
                </span>
                <span className="text-[10px] font-mono font-normal opacity-70">
                  [Call Function]
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="my-auto flex flex-col items-center justify-center py-6 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full border border-dashed border-zinc-700 bg-zinc-900/50 text-zinc-500">
            <Bot size={20} />
          </div>
          <div className="mt-2 text-xs text-zinc-400">
            Drop module here
          </div>
        </div>
      )}
    </div>
  );
}
