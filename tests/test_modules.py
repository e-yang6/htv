import unittest
from robot.modules.base import BaseRobotModule
from robot.modules.epipen import EpiPenModule
from robot.modules.medicine import MedicineModule
from robot.modules.registry import ModuleRegistry
from robot.server import app


class TestRobotModules(unittest.TestCase):
    def setUp(self):
        self.reg = ModuleRegistry()
        self.reg.register(EpiPenModule())
        self.reg.register(MedicineModule())

    def test_available_modules(self):
        modules = self.reg.get_available()
        self.assertEqual(len(modules), 2)
        ids = [m["id"] for m in modules]
        self.assertIn("epipen", ids)
        self.assertIn("medicine", ids)

    def test_epipen_left_arm_vs_right_arm(self):
        # Attach to left arm
        left_res = self.reg.attach("left_arm", "epipen")
        self.assertTrue(left_res["success"])
        self.assertEqual(left_res["exec_result"]["arm_config"]["approach_angle_deg"], 45)
        self.assertIn("Stabilization", left_res["exec_result"]["arm_config"]["role"])

        # Execute trigger on left arm
        left_trigger = self.reg.execute("left_arm", "trigger")
        self.assertTrue(left_trigger["success"])
        self.assertIn("stabilization", left_trigger["exec_result"]["message"].lower())

        # Attach to right arm
        right_res = self.reg.attach("right_arm", "epipen")
        self.assertTrue(right_res["success"])
        self.assertEqual(right_res["exec_result"]["arm_config"]["approach_angle_deg"], 90)
        self.assertIn("Primary", right_res["exec_result"]["arm_config"]["role"])

        # Execute trigger on right arm
        right_trigger = self.reg.execute("right_arm", "trigger")
        self.assertTrue(right_trigger["success"])
        self.assertIn("intramuscular", right_trigger["exec_result"]["message"].lower())

    def test_medicine_left_arm_vs_right_arm(self):
        # Attach to left arm
        left_res = self.reg.attach("left_arm", "medicine")
        self.assertTrue(left_res["success"])
        self.assertIn("Receptacle", left_res["exec_result"]["arm_config"]["role"])
        self.assertEqual(left_res["exec_result"]["arm_config"]["delivery_mode"], "Cup Drop Assisted")

        # Attach to right arm
        right_res = self.reg.attach("right_arm", "medicine")
        self.assertTrue(right_res["success"])
        self.assertIn("Patient Hand-off", right_res["exec_result"]["arm_config"]["role"])
        self.assertEqual(right_res["exec_result"]["arm_config"]["delivery_mode"], "Direct Blister Feed")

        # Dispense dose on right arm
        dispense = self.reg.execute("right_arm", "dispense")
        self.assertTrue(dispense["success"])
        self.assertEqual(dispense["exec_result"]["doses_remaining"], 4)

    def test_detach(self):
        self.reg.attach("left_arm", "epipen")
        self.assertIsNotNone(self.reg.get_attached()["left_arm"])

        detach_res = self.reg.detach("left_arm")
        self.assertTrue(detach_res["success"])
        self.assertIsNone(self.reg.get_attached()["left_arm"])

    def test_extensibility_custom_module(self):
        class FlashlightModule(BaseRobotModule):
            module_id = "flashlight"
            name = "LED Search Light"
            description = "High-lumen strobe and search light."
            supported_slots = ["left_arm", "right_arm"]

            def execute_feature(self, slot, action="default", params=None, robot_state=None):
                return {
                    "success": True,
                    "slot": slot,
                    "action": action,
                    "lumen": 1200 if slot == "right_arm" else 600
                }

        self.reg.register(FlashlightModule())
        self.assertEqual(len(self.reg.get_available()), 3)

        attach_res = self.reg.attach("right_arm", "flashlight")
        self.assertTrue(attach_res["success"])
        self.assertEqual(attach_res["exec_result"]["lumen"], 1200)


class TestFlaskServerEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_module_endpoints(self):
        # 1. Available modules
        resp = self.client.get("/modules/available")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.get_json()), 2)

        # 2. Attach
        resp = self.client.post("/modules/attach", json={"slot": "right_arm", "module_id": "epipen"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

        # 3. Status includes attached modules
        resp = self.client.get("/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("attached_modules", data)
        self.assertIsNotNone(data["attached_modules"]["right_arm"])

        # 4. Execute
        resp = self.client.post("/modules/execute", json={"slot": "right_arm", "action": "deploy"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

        # 5. Detach
        resp = self.client.post("/modules/detach", json={"slot": "right_arm"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
