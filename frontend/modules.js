/**
 * Robot Module System: Decoupled Architecture
 * 
 * Each component on the robot (EpiPen, Medicine dispenser, Flashlight, etc.)
 * is registered as a standalone module object with its own arm-specific behaviors
 * and feature execution functions.
 * 
 * To add a new module in the future, simply call:
 *   RobotModuleRegistry.register({ id: '...', name: '...', executeFeature: ... });
 * without touching the rest of the application.
 */

(function (window) {
  'use strict';

  // SVG Icons for clean, modern rendering
  const SVG_ICONS = {
    epipen: `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mod-icon-svg">
        <path d="m14 4 6 6-1.5 1.5-6-6L14 4z"></path>
        <path d="m18 10-9.5 9.5a2.12 2.12 0 0 1-3-3L15 7"></path>
        <path d="m4 20-2 2"></path>
        <path d="m8.5 10.5 5 5"></path>
        <path d="m7 15 2 2"></path>
        <path d="m17 3 4 4"></path>
      </svg>
    `,
    medicine: `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mod-icon-svg">
        <rect x="3" y="4" width="18" height="16" rx="3"></rect>
        <path d="M12 8v8"></path>
        <path d="M8 12h8"></path>
        <circle cx="12" cy="12" r="1.5" fill="currentColor"></circle>
      </svg>
    `,
    robotArmLeft: `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M5 18v-6a4 4 0 0 1 4-4h2"></path>
        <circle cx="5" cy="19" r="2"></circle>
        <rect x="11" y="6" width="10" height="4" rx="1"></rect>
      </svg>
    `,
    robotArmRight: `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M19 18v-6a4 4 0 0 0-4-4h-2"></path>
        <circle cx="19" cy="19" r="2"></circle>
        <rect x="3" y="6" width="10" height="4" rx="1"></rect>
      </svg>
    `
  };

  /**
   * Default Modules: EpiPen and Medicine
   */
  const DEFAULT_MODULES = [
    {
      id: 'epipen',
      name: 'EpiPen Auto-Injector',
      category: 'Emergency Medical',
      badge: 'Rapid Injection',
      color: '#ef4444',
      accentBg: 'rgba(239, 68, 68, 0.12)',
      borderColor: 'rgba(239, 68, 68, 0.35)',
      icon: SVG_ICONS.epipen,
      description: 'Epinephrine auto-injector module for rapid counteraction of acute allergic anaphylaxis.',
      supportedSlots: ['left_arm', 'right_arm'],
      slotBehaviors: {
        left_arm: {
          role: 'Stabilization & 45° Angled Hold',
          kinematics: 'Secondary stabilizer pose with safety interlock angle',
          defaultActionLabel: 'Deploy Stabilizer Pose',
          spec: 'Angle: 45° | Depth: 12mm | Mode: Assisted'
        },
        right_arm: {
          role: 'Direct Intramuscular Primary Actuation',
          kinematics: 'Perpendicular 90° high-torque injection stroke',
          defaultActionLabel: 'Arm Needle Actuator',
          spec: 'Angle: 90° | Depth: 15mm | Mode: Rapid Primary'
        }
      },

      /**
       * Called when module is attached to an arm.
       */
      onAttach: async function (slot, context = {}) {
        return {
          status: 'ready',
          safetyLock: true,
          message: `EpiPen successfully attached to ${slot === 'left_arm' ? 'Left Arm' : 'Right Arm'}.`
        };
      },

      /**
       * Called when module is detached from an arm.
       */
      onDetach: async function (slot, context = {}) {
        return {
          status: 'detached',
          message: `EpiPen detached from ${slot === 'left_arm' ? 'Left Arm' : 'Right Arm'}. Safety lock secured.`
        };
      },

      /**
       * The function that performs the EpiPen module's feature.
       * Once the team decides what the hardware/software routine does,
       * code it right here without affecting the rest of the application!
       */
      executeFeature: async function (slot, action = 'attach', context = {}) {
        const isLeft = slot === 'left_arm';
        const timestamp = new Date().toLocaleTimeString();

        // Slot-specific mechanics:
        if (action === 'attach') {
          return {
            success: true,
            module: 'epipen',
            slot: slot,
            action: 'attach',
            title: isLeft ? 'EpiPen Initialized (Left Arm)' : 'EpiPen Initialized (Right Arm)',
            message: isLeft
              ? 'Left arm calibrated: Angled 45° stabilizer mode active. Actuator stand-by.'
              : 'Right arm calibrated: Perpendicular 90° primary actuator armed. Safety interlock engaged.',
            telemetry: {
              slot,
              angleDeg: isLeft ? 45 : 90,
              depthMm: isLeft ? 12 : 15,
              mode: isLeft ? 'stabilizer' : 'primary_actuator'
            },
            timestamp
          };
        } else if (action === 'trigger' || action === 'deploy' || action === 'emergency') {
          // --- PLACEHOLDER: Connect solenoid / servo trigger hardware here ---
          return {
            success: true,
            module: 'epipen',
            slot: slot,
            action: action,
            title: isLeft ? 'EpiPen Deployed (Left Stabilizer)' : 'EpiPen Administered (Right Primary)',
            message: isLeft
              ? 'Executing 45° angled stabilization grip and counter-force hold.'
              : 'Direct 90° intramuscular injection cycle executed! Dosage delivered with auto-retract.',
            telemetry: {
              slot,
              doseDelivered: '0.3 mg epinephrine',
              strokeTimeMs: isLeft ? 1200 : 450,
              cycleComplete: true
            },
            timestamp
          };
        } else {
          return {
            success: true,
            module: 'epipen',
            slot: slot,
            action: action,
            title: `EpiPen Action: ${action}`,
            message: `Executed action '${action}' on ${isLeft ? 'Left Arm' : 'Right Arm'}.`,
            timestamp
          };
        }
      }
    },

    {
      id: 'medicine',
      name: 'Medicine Dispenser',
      category: 'Patient Care',
      badge: 'Prescription Delivery',
      color: '#3b82f6',
      accentBg: 'rgba(59, 130, 246, 0.12)',
      borderColor: 'rgba(59, 130, 246, 0.35)',
      icon: SVG_ICONS.medicine,
      description: 'Automated prescription medication carousel with dosage release and pill counting.',
      supportedSlots: ['left_arm', 'right_arm'],
      slotBehaviors: {
        left_arm: {
          role: 'Assisted Receptacle & Cup Cradle',
          kinematics: 'Horizontal cradle with 30° inward tilt for cup hold',
          defaultActionLabel: 'Prime Cup Receptacle',
          spec: 'Tilt: 30° | Mode: Cup Assisted | Inventory: 5 Doses'
        },
        right_arm: {
          role: 'Direct Patient Hand-off & Extension',
          kinematics: 'Forward reach with 15° decline presentation angle',
          defaultActionLabel: 'Dispense Next Dose',
          spec: 'Reach: +25cm | Mode: Direct Hand-off | Inventory: 5 Doses'
        }
      },

      onAttach: async function (slot, context = {}) {
        return {
          status: 'ready',
          dosesRemaining: 5,
          message: `Medicine Dispenser attached to ${slot === 'left_arm' ? 'Left Arm' : 'Right Arm'}. Inventory verified.`
        };
      },

      onDetach: async function (slot, context = {}) {
        return {
          status: 'detached',
          message: `Medicine Dispenser detached from ${slot === 'left_arm' ? 'Left Arm' : 'Right Arm'}. Carousel locked.`
        };
      },

      /**
       * The function that performs the Medicine Dispenser module's feature.
       * Once the team decides what the hardware/software routine does,
       * code it right here without affecting the rest of the application!
       */
      executeFeature: async function (slot, action = 'attach', context = {}) {
        const isLeft = slot === 'left_arm';
        const timestamp = new Date().toLocaleTimeString();

        if (action === 'attach') {
          return {
            success: true,
            module: 'medicine',
            slot: slot,
            action: 'attach',
            title: isLeft ? 'Medicine Ready (Left Arm)' : 'Medicine Ready (Right Arm)',
            message: isLeft
              ? 'Left arm receptacle primed: Receptive cup cradle aligned at 30° tilt.'
              : 'Right arm delivery primed: Forward extension carriage ready for patient hand-off.',
            telemetry: {
              slot,
              hopperLock: true,
              dosesRemaining: 5,
              presentationMode: isLeft ? 'cup_cradle' : 'patient_reach'
            },
            timestamp
          };
        } else if (action === 'trigger' || action === 'dispense' || action === 'emergency') {
          // --- PLACEHOLDER: Connect carousel stepper motor / solenoid gate hardware here ---
          return {
            success: true,
            module: 'medicine',
            slot: slot,
            action: action,
            title: isLeft ? 'Dose Prepared in Left Cradle' : 'Dose Dispensed via Right Arm',
            message: isLeft
              ? 'Pill released from hopper into left arm medical cup. Ready for collection.'
              : 'Right arm extended forward. Dispensing 1 prescribed dose directly to patient.',
            telemetry: {
              slot,
              dosesDispensed: 1,
              dosesRemaining: 4,
              carouselPosition: 2
            },
            timestamp
          };
        } else {
          return {
            success: true,
            module: 'medicine',
            slot: slot,
            action: action,
            title: `Medicine Action: ${action}`,
            message: `Executed action '${action}' on ${isLeft ? 'Left Arm' : 'Right Arm'}.`,
            timestamp
          };
        }
      }
    }
  ];

  /**
   * Robot Module Registry Singleton
   */
  class Registry {
    constructor() {
      this.modules = new Map();
      this.attached = {
        left_arm: null,
        right_arm: null
      };
      this.listeners = [];
      this.history = [];
      this.apiBase = 'http://localhost:5001';

      // Register default modules
      DEFAULT_MODULES.forEach(m => this.register(m));
    }

    setApiBase(url) {
      this.apiBase = url;
    }

    /**
     * Register a new module (clean plug-and-play architecture)
     */
    register(moduleDef) {
      if (!moduleDef || !moduleDef.id) {
        throw new Error('Module must have an id.');
      }
      this.modules.set(moduleDef.id, moduleDef);
      this._emitChange('register', { module: moduleDef });
    }

    getAll() {
      return Array.from(this.modules.values());
    }

    get(id) {
      return this.modules.get(id);
    }

    getAttached() {
      return { ...this.attached };
    }

    getHistory() {
      return [...this.history];
    }

    onStateChange(fn) {
      this.listeners.push(fn);
      return () => {
        this.listeners = this.listeners.filter(l => l !== fn);
      };
    }

    _emitChange(eventType, payload) {
      this.listeners.forEach(fn => {
        try {
          fn(eventType, payload, this.getAttached());
        } catch (e) {
          console.error('[ModuleRegistry] Listener error:', e);
        }
      });
    }

    _recordLog(entry) {
      this.history.unshift({
        id: Date.now() + Math.random().toString(36).substring(2, 5),
        time: new Date().toLocaleTimeString(),
        ...entry
      });
      if (this.history.length > 50) this.history.pop();
    }

    /**
     * Attach a module to a robot arm slot.
     * Recognizes new module and immediately invokes its feature function!
     */
    async attach(slot, moduleId, context = {}) {
      if (slot !== 'left_arm' && slot !== 'right_arm') {
        throw new Error(`Invalid slot: ${slot}`);
      }

      const mod = this.modules.get(moduleId);
      if (!mod) {
        throw new Error(`Module ${moduleId} not found.`);
      }

      // Detach previous module if exists
      const prev = this.attached[slot];
      if (prev && prev.id !== moduleId) {
        await this.detach(slot, context);
      }

      this.attached[slot] = mod;

      // 1. Run onAttach hook
      let attachInfo = {};
      if (typeof mod.onAttach === 'function') {
        try {
          attachInfo = await mod.onAttach(slot, context);
        } catch (e) {
          console.warn(`[ModuleRegistry] onAttach failed for ${moduleId}:`, e);
        }
      }

      // 2. Call the function that performs the module's feature upon attachment
      let execResult = null;
      if (typeof mod.executeFeature === 'function') {
        try {
          execResult = await mod.executeFeature(slot, 'attach', context);
        } catch (e) {
          console.error(`[ModuleRegistry] executeFeature failed for ${moduleId}:`, e);
          execResult = {
            success: false,
            title: `Error in ${mod.name}`,
            message: e.message,
            timestamp: new Date().toLocaleTimeString()
          };
        }
      }

      this._recordLog({
        type: 'attach',
        slot,
        moduleId: mod.id,
        moduleName: mod.name,
        result: execResult
      });

      this._emitChange('attach', {
        slot,
        module: mod,
        attachInfo,
        execResult
      });

      // Synchronize with backend API in background if online
      this._syncBackendAttach(slot, moduleId).catch(() => {});

      return {
        success: true,
        slot,
        module: mod,
        attachInfo,
        execResult
      };
    }

    /**
     * Detach module from a slot
     */
    async detach(slot, context = {}) {
      if (slot !== 'left_arm' && slot !== 'right_arm') return;
      const mod = this.attached[slot];
      if (!mod) return;

      this.attached[slot] = null;

      let detachInfo = {};
      if (typeof mod.onDetach === 'function') {
        try {
          detachInfo = await mod.onDetach(slot, context);
        } catch (e) {
          console.warn(`[ModuleRegistry] onDetach failed for ${mod.id}:`, e);
        }
      }

      this._recordLog({
        type: 'detach',
        slot,
        moduleId: mod.id,
        moduleName: mod.name,
        result: { message: `Detached from ${slot}` }
      });

      this._emitChange('detach', {
        slot,
        module: mod,
        detachInfo
      });

      this._syncBackendDetach(slot).catch(() => {});

      return { success: true, slot, detachedModule: mod };
    }

    /**
     * Execute a module's feature function on demand
     */
    async execute(slot, action = 'trigger', params = {}, context = {}) {
      const mod = this.attached[slot];
      if (!mod) {
        throw new Error(`No module attached to ${slot}`);
      }

      let execResult = null;
      if (typeof mod.executeFeature === 'function') {
        try {
          execResult = await mod.executeFeature(slot, action, { ...context, ...params });
        } catch (e) {
          console.error(`[ModuleRegistry] Execution error:`, e);
          execResult = {
            success: false,
            title: `Execution Failed`,
            message: e.message,
            timestamp: new Date().toLocaleTimeString()
          };
        }
      }

      this._recordLog({
        type: 'execute',
        slot,
        moduleId: mod.id,
        moduleName: mod.name,
        action,
        result: execResult
      });

      this._emitChange('execute', {
        slot,
        module: mod,
        action,
        execResult
      });

      this._syncBackendExecute(slot, action, params).catch(() => {});

      return execResult;
    }

    // Backend synchronizers (graceful fail if server offline)
    async _syncBackendAttach(slot, moduleId) {
      try {
        await fetch(`${this.apiBase}/modules/attach`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slot, module_id: moduleId })
        });
      } catch (_) {}
    }

    async _syncBackendDetach(slot) {
      try {
        await fetch(`${this.apiBase}/modules/detach`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slot })
        });
      } catch (_) {}
    }

    async _syncBackendExecute(slot, action, params) {
      try {
        await fetch(`${this.apiBase}/modules/execute`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slot, action, params })
        });
      } catch (_) {}
    }
  }

  // Export globally
  window.SVG_ICONS = SVG_ICONS;
  window.RobotModuleRegistry = new Registry();

})(window);
