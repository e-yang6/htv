const assert = require('assert');
const fs = require('fs');

// Create mock window environment
global.window = global;
global.fetch = async () => ({ json: async () => ({}) });

// Load modules.js
const code = fs.readFileSync('frontend/modules.js', 'utf8');
eval(code);

const registry = global.RobotModuleRegistry;
assert(registry, 'RobotModuleRegistry should be defined on window');

async function runTests() {
  console.log('Testing frontend modules.js...');

  // 1. Check default modules
  const modules = registry.getAll();
  assert.strictEqual(modules.length, 2, 'Should have 2 default modules');
  const ids = modules.map(m => m.id);
  assert(ids.includes('epipen'), 'Should have epipen');
  assert(ids.includes('medicine'), 'Should have medicine');

  // 2. Test EpiPen attachment & executeFeature on left_arm vs right_arm
  const leftAttach = await registry.attach('left_arm', 'epipen');
  assert.strictEqual(leftAttach.success, true);
  assert.strictEqual(leftAttach.execResult.telemetry.angleDeg, 45, 'Left arm should have 45 deg angle');
  assert.strictEqual(leftAttach.execResult.telemetry.mode, 'stabilizer');

  const rightAttach = await registry.attach('right_arm', 'epipen');
  assert.strictEqual(rightAttach.success, true);
  assert.strictEqual(rightAttach.execResult.telemetry.angleDeg, 90, 'Right arm should have 90 deg angle');
  assert.strictEqual(rightAttach.execResult.telemetry.mode, 'primary_actuator');

  // 3. Test EpiPen trigger
  const triggerRes = await registry.execute('right_arm', 'trigger');
  assert.strictEqual(triggerRes.success, true);
  assert(triggerRes.message.includes('Direct 90° intramuscular injection'));

  // 4. Test Medicine on left_arm vs right_arm
  await registry.attach('left_arm', 'medicine');
  const leftMed = registry.getAttached().left_arm;
  assert.strictEqual(leftMed.id, 'medicine');
  assert.strictEqual(leftMed.slotBehaviors.left_arm.role, 'Assisted Receptacle & Cup Cradle');

  const medDispense = await registry.execute('left_arm', 'trigger');
  assert.strictEqual(medDispense.success, true);
  assert(medDispense.message.includes('left arm medical cup'));

  // 5. Test Detach
  await registry.detach('left_arm');
  assert.strictEqual(registry.getAttached().left_arm, null);

  // 6. Test Extensibility (registering a future module without changing codebase)
  registry.register({
    id: 'flashlight',
    name: 'Tactical Flashlight',
    category: 'Utility',
    badge: 'Illumination',
    supportedSlots: ['left_arm', 'right_arm'],
    slotBehaviors: {
      left_arm: { role: 'Wide Ambient Floodlight' },
      right_arm: { role: 'Targeted High-Beam Strobe' }
    },
    executeFeature: async (slot, action) => ({
      success: true,
      slot,
      action,
      beam: slot === 'right_arm' ? 'strobe' : 'flood'
    })
  });

  assert.strictEqual(registry.getAll().length, 3);
  const flashAttach = await registry.attach('right_arm', 'flashlight');
  assert.strictEqual(flashAttach.execResult.beam, 'strobe');

  console.log('All frontend module tests passed successfully!');
}

runTests().catch(err => {
  console.error('Frontend tests failed:', err);
  process.exit(1);
});
