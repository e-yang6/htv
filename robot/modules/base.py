"""Base class for robot attachment modules.

Decoupled architecture:
Any new robot component (EpiPen, Medicine dispenser, Flashlight, Gripper, etc.)
inherits from BaseRobotModule and implements its arm-specific feature logic.
Once hardware routines or motor commands are ready, implement them inside
execute_feature() without changing the server API or UI code.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseRobotModule(ABC):
    module_id: str = "base"
    name: str = "Base Module"
    description: str = "Base robot attachment module"
    category: str = "general"
    supported_slots: List[str] = ["left_arm", "right_arm"]

    def __init__(self):
        pass

    def on_attach(self, slot: str, robot_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Hook called when the module is attached to a slot (left_arm or right_arm)."""
        return {
            "success": True,
            "module_id": self.module_id,
            "slot": slot,
            "message": f"{self.name} attached to {slot}."
        }

    def on_detach(self, slot: str, robot_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Hook called when the module is detached from a slot."""
        return {
            "success": True,
            "module_id": self.module_id,
            "slot": slot,
            "message": f"{self.name} detached from {slot}."
        }

    @abstractmethod
    def execute_feature(
        self,
        slot: str,
        action: str = "default",
        params: Optional[Dict[str, Any]] = None,
        robot_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute the module's core feature.
        
        Args:
            slot: 'left_arm' or 'right_arm'. Left and right arm mechanics
                  may alter the operational angle, reach, or sequence.
            action: Action verb (e.g. 'attach', 'trigger', 'deploy', 'calibrate').
            params: Optional execution parameters.
            robot_state: Current robot status (emergency, fall_waiting, direction, etc.).
            
        Returns:
            Dict containing execution results and telemetry.
        """
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Serialize module metadata for the API and UI."""
        return {
            "id": self.module_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "supported_slots": self.supported_slots,
        }
