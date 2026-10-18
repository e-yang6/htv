"""Module Registry managing robot arm components and dynamic execution."""

from collections import deque
from typing import Dict, Any, List, Optional
try:
    from robot.modules.base import BaseRobotModule
    from robot.modules.epipen import EpiPenModule
    from robot.modules.medicine import MedicineModule
except ModuleNotFoundError:
    from modules.base import BaseRobotModule
    from modules.epipen import EpiPenModule
    from modules.medicine import MedicineModule


class ModuleRegistry:
    def __init__(self):
        self._available_modules: Dict[str, BaseRobotModule] = {}
        # Slots currently available on the robot
        self._attached: Dict[str, Optional[BaseRobotModule]] = {
            "left_arm": None,
            "right_arm": None,
        }
        # Execution history / diagnostics log
        self._history: deque = deque(maxlen=50)

    def register(self, module: BaseRobotModule):
        """Register a new module type into the available pool."""
        self._available_modules[module.module_id] = module

    def get_available(self) -> List[Dict[str, Any]]:
        """List all available modules with metadata."""
        return [m.to_dict() for m in self._available_modules.values()]

    def get_attached(self) -> Dict[str, Optional[Dict[str, Any]]]:
        """Get currently attached modules by slot."""
        return {
            slot: (module.to_dict() if module else None)
            for slot, module in self._attached.items()
        }

    def get_history(self) -> List[Dict[str, Any]]:
        """Get recent module execution logs."""
        return list(self._history)

    def attach(
        self,
        slot: str,
        module_id: str,
        robot_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Attach a module to a designated arm slot and trigger its feature."""
        if slot not in self._attached:
            return {"success": False, "error": f"Invalid slot: {slot}. Must be 'left_arm' or 'right_arm'."}

        if module_id not in self._available_modules:
            return {"success": False, "error": f"Unknown module id: {module_id}"}

        module = self._available_modules[module_id]

        if slot not in module.supported_slots:
            return {"success": False, "error": f"Module {module.name} does not support slot {slot}."}

        # If something was already attached to this slot, detach it first
        prev_module = self._attached[slot]
        if prev_module and prev_module.module_id != module_id:
            prev_module.on_detach(slot, robot_state)

        # Attach new module
        self._attached[slot] = module
        attach_info = module.on_attach(slot, robot_state)

        # Immediately call the module's feature function upon attachment
        exec_result = module.execute_feature(
            slot=slot,
            action="attach",
            params=None,
            robot_state=robot_state
        )

        log_entry = {
            "type": "attach",
            "module_id": module.module_id,
            "module_name": module.name,
            "slot": slot,
            "exec_result": exec_result,
            "timestamp": exec_result.get("timestamp")
        }
        self._history.appendleft(log_entry)

        return {
            "success": True,
            "slot": slot,
            "module": module.to_dict(),
            "attach_info": attach_info,
            "exec_result": exec_result,
            "attached_state": self.get_attached()
        }

    def detach(
        self,
        slot: str,
        robot_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Detach any module from the designated arm slot."""
        if slot not in self._attached:
            return {"success": False, "error": f"Invalid slot: {slot}"}

        module = self._attached[slot]
        if not module:
            return {"success": True, "slot": slot, "message": f"Slot {slot} is already empty."}

        detach_info = module.on_detach(slot, robot_state)
        self._attached[slot] = None

        log_entry = {
            "type": "detach",
            "module_id": module.module_id,
            "module_name": module.name,
            "slot": slot,
            "message": f"Detached {module.name} from {slot}",
            "timestamp": detach_info.get("timestamp")
        }
        self._history.appendleft(log_entry)

        return {
            "success": True,
            "slot": slot,
            "detached_module": module.to_dict(),
            "detach_info": detach_info,
            "attached_state": self.get_attached()
        }

    def execute(
        self,
        slot: str,
        action: str = "trigger",
        params: Optional[Dict[str, Any]] = None,
        robot_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute the feature function of the module attached to slot."""
        if slot not in self._attached:
            return {"success": False, "error": f"Invalid slot: {slot}"}

        module = self._attached[slot]
        if not module:
            return {"success": False, "error": f"No module attached to {slot}."}

        exec_result = module.execute_feature(
            slot=slot,
            action=action,
            params=params,
            robot_state=robot_state
        )

        log_entry = {
            "type": "execute",
            "module_id": module.module_id,
            "module_name": module.name,
            "slot": slot,
            "action": action,
            "exec_result": exec_result,
            "timestamp": exec_result.get("timestamp")
        }
        self._history.appendleft(log_entry)

        return {
            "success": True,
            "slot": slot,
            "module": module.to_dict(),
            "exec_result": exec_result
        }


# Global registry singleton
registry = ModuleRegistry()
# Register default modules
registry.register(EpiPenModule())
registry.register(MedicineModule())
