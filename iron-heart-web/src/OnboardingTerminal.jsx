import React, { useState, useEffect, useRef } from "react";

const STORAGE_KEY = "ironheart_host_condition";
const SESSION_KEY = "ironheart_session_onboarded";

export default function OnboardingTerminal({ apiBase = "http://localhost:5001", isOpen, onClose, onConditionSet }) {
  const [condition, setCondition] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fadingOut, setFadingOut] = useState(false);
  const inputRef = useRef(null);

  // Initialize and check existing state
  useEffect(() => {
    let localSaved = "";
    try {
      localSaved = (localStorage.getItem(STORAGE_KEY) || "").trim();
    } catch {}

    if (localSaved && localSaved !== "Not specified" && localSaved !== "Severe Peanut Allergy (EpiPen equipped)") {
      setCondition(localSaved);
      if (onConditionSet) onConditionSet(localSaved);
    }

    // Check server profile
    fetch(apiBase + "/api/host/profile")
      .then((r) => r.json())
      .then((data) => {
        if (data && data.condition && data.condition !== "Not specified" && data.condition.trim()) {
          const s = data.condition.trim();
          setCondition(s);
          try { localStorage.setItem(STORAGE_KEY, s); } catch {}
          if (onConditionSet) onConditionSet(s);
        }
      })
      .catch(() => {});
  }, [apiBase]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setFadingOut(false);
      setIsSubmitting(false);
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen]);

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    const trimmed = condition.trim();
    if (!trimmed) return;

    setIsSubmitting(true);

    // Save locally
    try {
      localStorage.setItem(STORAGE_KEY, trimmed);
      sessionStorage.setItem(SESSION_KEY, "true");
    } catch {}

    // Sync with backend robot server
    try {
      await fetch(apiBase + "/api/host/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ condition: trimmed }),
      });
    } catch (err) {
      console.warn("[Onboarding] Backend offline, profile saved locally.");
    }

    if (onConditionSet) onConditionSet(trimmed);

    // Fade into UI
    setFadingOut(true);
    setTimeout(() => {
      onClose();
    }, 600);
  };

  const fillChip = (val) => {
    setCondition(val);
    inputRef.current?.focus();
  };

  if (!isOpen) return null;

  return (
    <div
      className={`fixed inset-0 z-[100] flex items-center justify-center p-4 transition-all duration-700 ${
        fadingOut ? "opacity-0 backdrop-blur-none pointer-events-none scale-95" : "opacity-100 backdrop-blur-md"
      }`}
      style={{
        background: "rgba(0, 0, 0, 0.88)",
      }}
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-lg border border-zinc-800 bg-black font-mono text-zinc-100 shadow-2xl"
        role="dialog"
        aria-modal="true"
      >
        {/* Minimal Terminal Header: Just inactive aesthetic dots, no skip/close */}
        <div className="flex items-center gap-2 border-b border-zinc-900 bg-zinc-950/60 px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-zinc-700/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-zinc-800/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-zinc-800/60" />
        </div>

        {/* Terminal Body */}
        <div className="p-6">
          <div className="mb-4 text-xs text-zinc-400">
            enter primary condition:
          </div>

          {/* Input Form with blinking / symbol */}
          <form onSubmit={handleSubmit} className="flex items-center gap-2">
            <span className="animate-pulse select-none text-base font-bold text-zinc-300">/</span>
            <input
              ref={inputRef}
              type="text"
              value={condition}
              onChange={(e) => setCondition(e.target.value)}
              disabled={isSubmitting}
              className="flex-1 bg-transparent text-sm text-zinc-100 outline-none caret-zinc-400"
              autoComplete="off"
              autoFocus
              required
            />
            {condition.trim() && (
              <button
                type="submit"
                disabled={isSubmitting}
                className="text-xs text-zinc-500 hover:text-zinc-200 transition-colors"
              >
                ↵
              </button>
            )}
          </form>

          {/* Quick select */}
          <div className="mt-8 flex flex-wrap items-center gap-2 pt-4 border-t border-zinc-900">
            {[
              "Severe Peanut Allergy",
              "Type 1 Diabetes",
              "Severe Asthma",
              "Cardiac History / Pacemaker Alert",
            ].map((chip, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => fillChip(chip)}
                className="rounded border border-zinc-800 bg-zinc-950 px-2.5 py-1 text-xs text-zinc-500 transition-colors hover:border-zinc-700 hover:text-zinc-300"
              >
                {chip}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
