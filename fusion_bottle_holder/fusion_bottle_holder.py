import adsk.core, adsk.fusion, traceback

def run(context):
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = app.activeProduct
        rootComp = design.rootComponent

        # All in cm
        BAR_THICK = 0.5
        BAR_GAP = 0.03
        CLIP_W = 2.5
        CLIP_ARM = 0.5
        WALL = 0.2       # clip arm thickness
        TOOTH = 0.15

        BOTTLE_D = 3.3      # measured ~3.2cm + snug fit
        BOTTLE_R = BOTTLE_D / 2
        RING_WALL = 0.3
        RING_LEN = 2.0

        sketches = rootComp.sketches
        extrudes = rootComp.features.extrudeFeatures
        xy = rootComp.xYConstructionPlane

        slot_h = BAR_THICK + BAR_GAP * 2
        clip_hw = CLIP_W / 2
        clip_outer_hw = clip_hw + WALL
        ring_outer_r = BOTTLE_R + RING_WALL

        ring_cy = -ring_outer_r
        block_top = slot_h + CLIP_ARM
        ring_bot = ring_cy - ring_outer_r

        # STEP 1: T-shaped body (narrow clip arms, wide ring base)
        sk = sketches.add(xy)
        L = sk.sketchCurves.sketchLines
        pts = [
            (-ring_outer_r, ring_bot),
            (-ring_outer_r, 0),
            (-clip_outer_hw, 0),
            (-clip_outer_hw, block_top),
            (clip_outer_hw, block_top),
            (clip_outer_hw, 0),
            (ring_outer_r, 0),
            (ring_outer_r, ring_bot),
        ]
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            L.addByTwoPoints(
                adsk.core.Point3D.create(pts[i][0], pts[i][1], 0),
                adsk.core.Point3D.create(pts[j][0], pts[j][1], 0))

        extrudes.addSimple(sk.profiles.item(0),
            adsk.core.ValueInput.createByReal(RING_LEN),
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

        # STEP 2: Cut bar slot — open at top
        sk2 = sketches.add(xy)
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

        # STEP 3: Snap teeth
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

        # STEP 4: Cut bottle hole
        sk3 = sketches.add(xy)
        sk3.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, ring_cy, 0), BOTTLE_R)

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

        ui.messageBox('Bottle holder generated!')

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
