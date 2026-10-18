/**
 * Decoupled Robot Module Architecture
 * 
 * Defines available modules (EpiPen, Medicine Dispenser),
 * with 1 decoupled action each.
 */

export const MODULE_DEFINITIONS = [
  {
    id: "epipen",
    name: "EpiPen Carrier",
    color: "#ef4444",
    accentBg: "rgba(239, 68, 68, 0.12)",
    borderColor: "rgba(239, 68, 68, 0.35)",
    glowColor: "rgba(239, 68, 68, 0.25)",
    iconName: "Syringe",
    description: "Carries an EpiPen so the robot can bring it to someone having an allergic reaction.",
    supportedSlots: ["left_arm", "right_arm"],
    actions: [
      {
        id: "trigger",
        label: "Deliver EpiPen",
        type: "primary",
        description: "Extends the arm to hand off the EpiPen.",
        handler: async ({ slot }) => {
          return { status: "delivered", action: "trigger", message: `EpiPen delivered via ${slot === "left_arm" ? "Left Arm" : "Right Arm"}.` };
        }
      }
    ]
  },
  {
    id: "medicine",
    name: "Medicine Carrier",
    color: "#10b981",
    accentBg: "rgba(16, 185, 129, 0.12)",
    borderColor: "rgba(16, 185, 129, 0.35)",
    glowColor: "rgba(16, 185, 129, 0.25)",
    iconName: "Pill",
    description: "Holds a medicine bottle so the robot can deliver medication to someone who needs it.",
    supportedSlots: ["left_arm", "right_arm"],
    actions: [
      {
        id: "dispense",
        label: "Deliver Medicine",
        type: "primary",
        description: "Extends the arm to hand off the medicine bottle.",
        handler: async ({ slot }) => {
          return { status: "delivered", action: "dispense", message: `Medicine delivered via ${slot === "left_arm" ? "Left Arm" : "Right Arm"}.` };
        }
      }
    ]
  }
];

export const INITIAL_ATTACHED = {
  left_arm: null,
  right_arm: null,
};
