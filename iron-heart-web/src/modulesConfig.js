/**
 * Decoupled Robot Module Architecture
 * 
 * Defines available modules (EpiPen, Medicine Dispenser),
 * with 1 decoupled action each.
 */

export const MODULE_DEFINITIONS = [
  {
    id: "epipen",
    name: "EpiPen Auto-Injector",
    color: "#ef4444",
    accentBg: "rgba(239, 68, 68, 0.12)",
    borderColor: "rgba(239, 68, 68, 0.35)",
    glowColor: "rgba(239, 68, 68, 0.25)",
    iconName: "Syringe",
    description: "Emergency epinephrine auto-injector designed to counteract acute anaphylaxis and severe allergic shock.",
    supportedSlots: ["left_arm", "right_arm"],
    actions: [
      {
        id: "trigger",
        label: "Administer Injection",
        type: "primary",
        description: "Disengages safety lock and executes solenoid needle extension.",
        handler: async ({ slot, robotState }) => {
          return {
            status: "executed",
            action: "trigger",
            safetyLock: false,
            deliveredDose: "0.3mg Epinephrine",
            message: `EpiPen actuated on ${slot === "left_arm" ? "Left Arm" : "Right Arm"}. Safety lock released, dose delivered.`
          };
        }
      }
    ]
  },
  {
    id: "medicine",
    name: "Medicine Bottle Dispenser",
    color: "#10b981",
    accentBg: "rgba(16, 185, 129, 0.12)",
    borderColor: "rgba(16, 185, 129, 0.35)",
    glowColor: "rgba(16, 185, 129, 0.25)",
    iconName: "Pill",
    description: "Smart medication dispenser with automated dosage release, blister feed, and patient hand-off.",
    supportedSlots: ["left_arm", "right_arm"],
    actions: [
      {
        id: "dispense",
        label: "Dispense Single Dose",
        type: "primary",
        description: "Rotates carousel and drops prescribed dosage into hopper / hand-off tray.",
        handler: async ({ slot, robotState }) => {
          return {
            status: "dispensed",
            action: "dispense",
            doseId: "DOSE-" + Math.floor(1000 + Math.random() * 9000),
            message: `Medication dose dispensed via ${slot === "left_arm" ? "Left Arm" : "Right Arm"}.`
          };
        }
      }
    ]
  }
];

export const INITIAL_ATTACHED = {
  left_arm: null,
  right_arm: null,
};
