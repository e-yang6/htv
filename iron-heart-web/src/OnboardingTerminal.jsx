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
    <div className="backdrop" style={fadingOut ? { opacity: 0, transition: "opacity .3s" } : undefined}>
      <form className="dialog" role="dialog" aria-modal="true" onSubmit={handleSubmit}>
        <h2>Host's medical condition</h2>
        <p>Shown to helpers and read out by the robot in an emergency.</p>
        <input
          ref={inputRef}
          type="text"
          value={condition}
          onChange={(e) => setCondition(e.target.value)}
          disabled={isSubmitting}
          placeholder="e.g. Type 1 Diabetes"
          autoComplete="off"
          autoFocus
          required
        />
        <div className="presets">
          {[
            "Severe Peanut Allergy",
            "Type 1 Diabetes",
            "Severe Asthma",
            "Cardiac History / Pacemaker Alert",
          ].map((chip) => (
            <button key={chip} type="button" onClick={() => fillChip(chip)} className="btn">{chip}</button>
          ))}
        </div>
        <button type="submit" disabled={isSubmitting || !condition.trim()} className="btn btn-primary">Save</button>
      </form>
    </div>
  );
}
