import React, { useState, useEffect, useRef } from "react";

const STORAGE_KEY = "ironheart_host_condition";
const SESSION_KEY = "ironheart_session_onboarded";
const PROFILE_KEY = "ironheart_host_profile";   // {description, steps} for a condition typed in by hand
// These have built-in helper instructions (EMERGENCY_INSTRUCTIONS in main.jsx); anything else asks for its own
export const PRESET_CONDITIONS = [
  "Severe Peanut Allergy",
  "Type 1 Diabetes",
  "Severe Asthma",
  "Cardiac History / Pacemaker Alert",
];
const isPreset = (c) => PRESET_CONDITIONS.includes(c.trim());
const toSteps = (text) => text.split("\n").map(l => l.replace(/^\s*(\d+[.)]|[-*•])\s*/, "").trim()).filter(Boolean);

export default function OnboardingTerminal({ apiBase = "http://localhost:5001", isOpen, onClose, onConditionSet }) {
  const [condition, setCondition] = useState("");
  const [description, setDescription] = useState("");
  const [stepsText, setStepsText] = useState("");
  const descriptionRef = useRef(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fadingOut, setFadingOut] = useState(false);
  const inputRef = useRef(null);

  // Initialize and check existing state
  useEffect(() => {
    let localSaved = "";
    try {
      localSaved = (localStorage.getItem(STORAGE_KEY) || "").trim();
    } catch {}

    let localProfile = { description: "", steps: [] };
    try { localProfile = { ...localProfile, ...JSON.parse(localStorage.getItem(PROFILE_KEY) || "{}") }; } catch {}

    if (localSaved && localSaved !== "Not specified" && localSaved !== "Severe Peanut Allergy (EpiPen equipped)") {
      setCondition(localSaved);
      setDescription(localProfile.description || "");
      setStepsText((localProfile.steps || []).join("\n"));
      if (onConditionSet) onConditionSet(localSaved, localProfile);
    }

    // Check server profile
    fetch(apiBase + "/api/host/profile")
      .then((r) => r.json())
      .then((data) => {
        if (data && data.condition && data.condition !== "Not specified" && data.condition.trim()) {
          const s = data.condition.trim();
          const profile = { description: data.description || "", steps: data.steps || [] };
          setCondition(s);
          setDescription(profile.description);
          setStepsText(profile.steps.join("\n"));
          try {
            localStorage.setItem(STORAGE_KEY, s);
            localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
          } catch {}
          if (onConditionSet) onConditionSet(s, profile);
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
    // A condition typed in by hand: Enter in the condition box moves on to its description / steps
    if (!isPreset(trimmed) && document.activeElement === inputRef.current) {
      descriptionRef.current?.focus();
      return;
    }
    const profile = isPreset(trimmed) ? { description: "", steps: [] }
      : { description: description.trim(), steps: toSteps(stepsText) };

    setIsSubmitting(true);

    // Save locally
    try {
      localStorage.setItem(STORAGE_KEY, trimmed);
      localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
      sessionStorage.setItem(SESSION_KEY, "true");
    } catch {}

    // Sync with backend robot server
    try {
      await fetch(apiBase + "/api/host/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ condition: trimmed, ...profile }),
      });
    } catch (err) {
      console.warn("[Onboarding] Backend offline, profile saved locally.");
    }

    if (onConditionSet) onConditionSet(trimmed, profile);

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

          {/* A condition typed in by hand: what it is, and what a helper should do */}
          {condition.trim() && !isPreset(condition) && (
            <div className="mt-6 space-y-4">
              <label className="block">
                <span className="text-xs text-zinc-400">describe it (shown to helpers):</span>
                <textarea
                  ref={descriptionRef}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={isSubmitting}
                  rows={2}
                  placeholder="e.g. Epilepsy — may have a seizure after a fall"
                  className="mt-2 w-full resize-y border border-zinc-800 bg-zinc-950 p-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
                />
              </label>
              <label className="block">
                <span className="text-xs text-zinc-400">steps for a helper, one per line:</span>
                <textarea
                  value={stepsText}
                  onChange={(e) => setStepsText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit(e); }}
                  disabled={isSubmitting}
                  rows={5}
                  placeholder={"Call 911\nTurn them on their side\nTime the seizure; don't hold them down"}
                  className="mt-2 w-full resize-y border border-zinc-800 bg-zinc-950 p-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
                />
              </label>
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-zinc-600">blank steps = general first-aid steps</span>
                <button type="button" onClick={() => handleSubmit()} disabled={isSubmitting}
                        className="border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 hover:text-zinc-100">
                  save ↵
                </button>
              </div>
            </div>
          )}

          {/* Quick select */}
          <div className="mt-8 flex flex-wrap items-center gap-2 pt-4 border-t border-zinc-900">
            {PRESET_CONDITIONS.map((chip, idx) => (
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
