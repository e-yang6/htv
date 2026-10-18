"""Medicine Dispenser robot arm module.

Decoupled feature implementation:
Modify execute_feature() or the slot-specific subroutines below when
the dispensing hardware (stepper carousel, solenoid hatch, pill counter) is finalized.
"""

import time
from typing import Dict, Any, Optional

try:
    from robot.modules.base import BaseRobotModule
except ModuleNotFoundError:
    from modules.base import BaseRobotModule


class MedicineModule(BaseRobotModule):
    module_id = "medicine"
    name = "Medicine Dispenser"
    description = "Automated oral medication dispensing module with dosage tracking."
    category = "patient_care"
    supported_slots = ["left_arm", "right_arm"]

    def __init__(self):
        super().__init__()
        self.doses_remaining = 5
        self.compartment_locked = True

    def on_attach(self, slot: str, robot_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Recognize that Medicine Dispenser has been mounted onto the robot."""
        return {
            "success": True,
            "module_id": self.module_id,
            "slot": slot,
            "message": f"Medicine Dispenser recognized on {slot}. Inventory: {self.doses_remaining} doses available.",
            "doses_remaining": self.doses_remaining
        }

    def execute_feature(
        self,
        slot: str,
        action: str = "default",
        params: Optional[Dict[str, Any]] = None,
        robot_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute Medicine Dispenser feature, considering left vs right arm functionality."""
        timestamp = time.strftime('%H:%M:%S')

        # Arm-specific functionality differences:
        # - Left arm: Assisted receptacle cradle / cup holding
        # - Right arm: Direct patient hand-off / extended carousel feed
        if slot == "left_arm":
            arm_config = {
                "role": "Assisted Receptacle & Hopper Cradle",
                "tray_orientation": "Horizontal Stabilized (45° inward)",
                "delivery_mode": "Cup Drop Assisted"
            }
        elif slot == "right_arm":
            arm_config = {
                "role": "Direct Patient Hand-off & Extension",
                "tray_orientation": "Forward Reach (15° decline)",
                "delivery_mode": "Direct Blister Feed"
            }
        else:
            arm_config = {
                "role": "Standard Dispenser",
                "tray_orientation": "Default",
                "delivery_mode": "Standard Drop"
            }

        if action in ["attach", "default"]:
            # Initial feature recognition routine upon attachment
            return {
                "success": True,
                "module_id": self.module_id,
                "slot": slot,
                "action": action,
                "title": f"Medicine Dispenser Ready ({slot.replace('_', ' ').title()})",
                "message": (
                    f"Medicine Dispenser recognized on {slot}. Configured for {arm_config['role']}. "
                    f"Delivery mode: {arm_config['delivery_mode']}."
                ),
                "arm_config": arm_config,
                "doses_remaining": self.doses_remaining,
                "timestamp": timestamp
            }

        elif action in ["dispense", "trigger", "emergency"]:
            # Feature execution: Dispense pill or dose
            # NOTE: When stepper motor / solenoid hatch is built, add actuation call here.
            if self.doses_remaining > 0:
                self.doses_remaining -= 1
                dispensed = True
                msg = (
                    f"Dose successfully dispensed via {slot} ({arm_config['delivery_mode']}). "
                    f"Remaining inventory: {self.doses_remaining} doses."
                )
            else:
                dispensed = False
                msg = f"Dispenser on {slot} is empty! Please refill medication cartridge."

            return {
                "success": dispensed,
                "module_id": self.module_id,
                "slot": slot,
                "action": action,
                "title": f"Dose Dispensed ({slot.replace('_', ' ').title()})" if dispensed else "Dispenser Empty",
                "message": msg,
                "arm_config": arm_config,
                "doses_remaining": self.doses_remaining,
                "timestamp": timestamp
            }

        elif action == "check_inventory":
            return {
                "success": True,
                "module_id": self.module_id,
                "slot": slot,
                "action": action,
                "title": "Medication Inventory",
                "message": f"Cartridge status: {self.doses_remaining} standard doses available.",
                "arm_config": arm_config,
                "doses_remaining": self.doses_remaining,
                "timestamp": timestamp
            }

        else:
            return {
                "success": True,
                "module_id": self.module_id,
                "slot": slot,
                "action": action,
                "title": f"Medicine Action: {action}",
                "message": f"Executed custom action '{action}' on {slot}.",
                "arm_config": arm_config,
                "timestamp": timestamp
            }
