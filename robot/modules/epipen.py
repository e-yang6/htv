"""EpiPen Auto-Injector robot arm module.

Decoupled feature implementation:
Modify execute_feature() or the slot-specific subroutines below when
the hardware actuation (solenoid, servo angle, injection trigger) is finalized.
"""

import time
from typing import Dict, Any, Optional

try:
    from robot.modules.base import BaseRobotModule
except ModuleNotFoundError:
    from modules.base import BaseRobotModule


class EpiPenModule(BaseRobotModule):
    module_id = "epipen"
    name = "EpiPen Auto-Injector"
    description = "Emergency epinephrine injection unit for severe allergic reactions."
    category = "emergency_medical"
    supported_slots = ["left_arm", "right_arm"]

    def __init__(self):
        super().__init__()
        self.safety_lock = True
        self.dose_available = True

    def on_attach(self, slot: str, robot_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Recognize that EpiPen has been mounted onto the robot."""
        self.safety_lock = True
        return {
            "success": True,
            "module_id": self.module_id,
            "slot": slot,
            "message": f"EpiPen Auto-Injector securely docked onto {slot}.",
            "safety_lock": self.safety_lock,
            "dose_available": self.dose_available
        }

    def execute_feature(
        self,
        slot: str,
        action: str = "default",
        params: Optional[Dict[str, Any]] = None,
        robot_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute EpiPen feature, considering left vs right arm functionality."""
        timestamp = time.strftime('%H:%M:%S')

        # Arm-specific functionality differences:
        # - Left arm: Designed for angled stabilization / secondary approach
        # - Right arm: Designed for direct vertical / primary intramuscular injection
        if slot == "left_arm":
            arm_config = {
                "role": "Stabilization & Angled Deployment",
                "approach_angle_deg": 45,
                "injection_depth_mm": 12.0,
                "stroke_speed": "controlled_smooth"
            }
        elif slot == "right_arm":
            arm_config = {
                "role": "Direct Intramuscular Primary Actuation",
                "approach_angle_deg": 90,
                "injection_depth_mm": 15.0,
                "stroke_speed": "rapid_impact"
            }
        else:
            arm_config = {
                "role": "Standard Actuation",
                "approach_angle_deg": 0,
                "injection_depth_mm": 10.0,
                "stroke_speed": "standard"
            }

        if action in ["attach", "default"]:
            # Initial feature recognition routine upon attachment
            return {
                "success": True,
                "module_id": self.module_id,
                "slot": slot,
                "action": action,
                "title": f"EpiPen Ready ({slot.replace('_', ' ').title()})",
                "message": (
                    f"EpiPen system recognized on {slot}. Configured as {arm_config['role']} "
                    f"at {arm_config['approach_angle_deg']}° approach."
                ),
                "arm_config": arm_config,
                "safety_lock": self.safety_lock,
                "timestamp": timestamp
            }

        elif action in ["deploy", "trigger", "emergency"]:
            # Feature execution: Administer or trigger EpiPen
            # NOTE: When hardware is built, connect motor / solenoid trigger code here.
            self.safety_lock = False
            return {
                "success": True,
                "module_id": self.module_id,
                "slot": slot,
                "action": action,
                "title": f"EpiPen Deployed ({slot.replace('_', ' ').title()})",
                "message": (
                    f"EpiPen sequence executed on {slot}. {arm_config['role']} active. "
                    f"Delivering dosage with {arm_config['approach_angle_deg']}° injection vector."
                ),
                "arm_config": arm_config,
                "safety_lock": self.safety_lock,
                "timestamp": timestamp
            }

        elif action == "calibrate":
            return {
                "success": True,
                "module_id": self.module_id,
                "slot": slot,
                "action": action,
                "title": f"EpiPen Calibrated ({slot.replace('_', ' ').title()})",
                "message": f"EpiPen alignment verified on {slot} ({arm_config['approach_angle_deg']}°). Ready for dispatch.",
                "arm_config": arm_config,
                "timestamp": timestamp
            }

        else:
            return {
                "success": True,
                "module_id": self.module_id,
                "slot": slot,
                "action": action,
                "title": f"EpiPen Action: {action}",
                "message": f"Executed custom action '{action}' on {slot}.",
                "arm_config": arm_config,
                "timestamp": timestamp
            }
