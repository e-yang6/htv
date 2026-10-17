import adsk.core, adsk.fusion, traceback

def run(context):
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = app.activeProduct
        rootComp = design.rootComponent

        # All in cm
        BAR_THICK = 0.5     # thickness of the middle section
        BAR_GAP = 0.03      # clearance
        CLIP_W = 2.5        # matches bar width
        CLIP_ARM = 0.5      # arm height above the bar
        WALL = 0.2
        TOOTH = 0.15

        PEN_D = 2.8         # epipen ~2.7cm long side + snug fit
        PEN_R = PEN_D / 2
        RING_WALL = 0.25
        RING_LEN = 1.5      # ring width along the pen

        sketches = rootComp.sketches
        extrudes = rootComp.features.extrudeFeatures
        xy = rootComp.xYConstructionPlane

        slot_h = BAR_THICK + BAR_GAP * 2
        clip_hw = CLIP_W / 2

        # Ring center below the clip
        ring_cy = -(WALL + PEN_R + RING_WALL)

        # STEP 1: Clip body — two arms + base connecting to ring
        # One solid profile: base + arms + ring area
        block_top = slot_h + CLIP_ARM
        block_bot = ring_cy - PEN_R - RING_WALL
        block_hw = max(clip_hw + WALL, PEN_R + RING_WALL)

        sk = sketches.add(xy)
        L = sk.sketchCurves.sketchLines
        L.addByTwoPoints(adsk.core.Point3D.create(-block_hw, block_bot, 0),
                         adsk.core.Point3D.create(-block_hw, block_top, 0))
        L.addByTwoPoints(adsk.core.Point3D.create(-block_hw, block_top, 0),
                         adsk.core.Point3D.create(block_hw, block_top, 0))
        L.addByTwoPoints(adsk.core.Point3D.create(block_hw, block_top, 0),
                         adsk.core.Point3D.create(block_hw, block_bot, 0))
        L.addByTwoPoints(adsk.core.Point3D.create(block_hw, block_bot, 0),
                         adsk.core.Point3D.create(-block_hw, block_bot, 0))

        extrudes.addSimple(sk.profiles.item(0),
            adsk.core.ValueInput.createByReal(RING_LEN),
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

        # STEP 2: Cut bar slot — open at top so it snaps on
        sk2 = sketches.add(xy)
        shw = (BAR_THICK + BAR_GAP * 2) / 2
        # Slot is horizontal: bar is thin (0.5cm), clip jaws come from left and right
        # Actually the bar is flat and horizontal. The slot opens upward.
        # Slot: CLIP_W wide, BAR_THICK tall, open at top
        sk2l = sk2.sketchCurves.sketchLines
        sk2l.addByTwoPoints(adsk.core.Point3D.create(-clip_hw, 0, 0),
                            adsk.core.Point3D.create(-clip_hw, block_top + 1, 0))
        sk2l.addByTwoPoints(adsk.core.Point3D.create(-clip_hw, block_top + 1, 0),
                            adsk.core.Point3D.create(clip_hw, block_top + 1, 0))
        sk2l.addByTwoPoints(adsk.core.Point3D.create(clip_hw, block_top + 1, 0),
                            adsk.core.Point3D.create(clip_hw, 0, 0))
        sk2l.addByTwoPoints(adsk.core.Point3D.create(clip_hw, 0, 0),
                            adsk.core.Point3D.create(-clip_hw, 0, 0))

        extrudes.addSimple(sk2.profiles.item(0),
            adsk.core.ValueInput.createByReal(RING_LEN),
            adsk.fusion.FeatureOperations.CutFeatureOperation)

        # STEP 3: Snap teeth — bumps near top of each arm, pointing inward
        for side in [-1, 1]:
            skt = sketches.add(xy)
            if side == -1:
                tx = -clip_hw
            else:
                tx = clip_hw - TOOTH
            ty = block_top - 0.3

            Lt = skt.sketchCurves.sketchLines
            Lt.addByTwoPoints(adsk.core.Point3D.create(tx, ty, 0),
                              adsk.core.Point3D.create(tx, block_top, 0))
            Lt.addByTwoPoints(adsk.core.Point3D.create(tx, block_top, 0),
                              adsk.core.Point3D.create(tx + TOOTH, block_top, 0))
            Lt.addByTwoPoints(adsk.core.Point3D.create(tx + TOOTH, block_top, 0),
                              adsk.core.Point3D.create(tx + TOOTH, ty, 0))
            Lt.addByTwoPoints(adsk.core.Point3D.create(tx + TOOTH, ty, 0),
                              adsk.core.Point3D.create(tx, ty, 0))

            extrudes.addSimple(skt.profiles.item(0),
                adsk.core.ValueInput.createByReal(RING_LEN),
                adsk.fusion.FeatureOperations.JoinFeatureOperation)

        # STEP 4: Cut pen hole — full circle, pen slides in from end
        sk3 = sketches.add(xy)
        sk3.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, ring_cy, 0), PEN_R)

        circProf = None
        for i in range(sk3.profiles.count):
            p = sk3.profiles.item(i)
            bb = p.boundingBox
            w = bb.maxPoint.x - bb.minPoint.x
            if circProf is None or w < (circProf.boundingBox.maxPoint.x - circProf.boundingBox.minPoint.x):
                circProf = p

        if circProf:
            extrudes.addSimple(circProf,
                adsk.core.ValueInput.createByReal(RING_LEN),
                adsk.fusion.FeatureOperations.CutFeatureOperation)

        ui.messageBox('EpiPen holder generated!')

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
