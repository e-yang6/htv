#Author: Generated for HTV project
#Description: Minimal chest piece — absolute fastest print time
#             Fits full Arduino TinyML Kit (Nano 33 BLE Sense + OV7675 + Shield)

import adsk.core, adsk.fusion, adsk.cam, traceback, math

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = app.activeProduct
        rootComp = design.rootComponent

        # ==============================================
        # PARAMETERS (all in cm)
        # ==============================================

        # Kit pocket (user measured)
        KIT_L = 8.0
        KIT_W = 4.0
        KIT_H = 2.0
        KIT_CLEARANCE = 0.05

        # Minimal structure
        WALL = 0.1                # 1mm walls (minimum viable for FDM)
        BASE = 0.08               # 0.8mm base (4 layers at 0.2mm)
        CLIP_W = 0.3
        CLIP_D = 0.1
        CLIP_H = 0.12
        TAB_W = 0.8
        TAB_L = 1.0
        HOLE_R = 0.2
        USB_W = 0.4
        LENS_R = 0.5

        sketches = rootComp.sketches
        xyPlane = rootComp.xYConstructionPlane
        extrudes = rootComp.features.extrudeFeatures

        kl = (KIT_L / 2) + KIT_CLEARANCE
        kw = (KIT_W / 2) + KIT_CLEARANCE

        # =============================================
        # STEP 1: Base plate — ONLY under the kit, not a disc
        # Just a rectangle, no wasted material
        # =============================================
        margin = WALL + 0.05
        sk_base = sketches.add(xyPlane)
        lb = sk_base.sketchCurves.sketchLines
        lb.addByTwoPoints(
            adsk.core.Point3D.create(-kl - margin, -kw - margin, 0),
            adsk.core.Point3D.create(kl + margin, -kw - margin, 0))
        lb.addByTwoPoints(
            adsk.core.Point3D.create(kl + margin, -kw - margin, 0),
            adsk.core.Point3D.create(kl + margin, kw + margin, 0))
        lb.addByTwoPoints(
            adsk.core.Point3D.create(kl + margin, kw + margin, 0),
            adsk.core.Point3D.create(-kl - margin, kw + margin, 0))
        lb.addByTwoPoints(
            adsk.core.Point3D.create(-kl - margin, kw + margin, 0),
            adsk.core.Point3D.create(-kl - margin, -kw - margin, 0))

        if sk_base.profiles.count > 0:
            ext_base = extrudes.createInput(
                sk_base.profiles.item(0),
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            ext_base.setDistanceExtent(False,
                adsk.core.ValueInput.createByReal(BASE))
            bf = extrudes.add(ext_base)
            bf.bodies.item(0).name = "ChestPiece"

        # =============================================
        # STEP 2: Pocket walls (4 thin walls around the kit)
        # =============================================
        walls = [
            (-kl - WALL, -kw - WALL, -kl, kw + WALL),
            (kl, -kw - WALL, kl + WALL, kw + WALL),
            (-kl - WALL, -kw - WALL, kl + WALL, -kw),
            (-kl - WALL, kw, kl + WALL, kw + WALL),
        ]

        for x0, y0, x1, y1 in walls:
            sk = sketches.add(xyPlane)
            ln = sk.sketchCurves.sketchLines
            ln.addByTwoPoints(
                adsk.core.Point3D.create(x0, y0, 0),
                adsk.core.Point3D.create(x1, y0, 0))
            ln.addByTwoPoints(
                adsk.core.Point3D.create(x1, y0, 0),
                adsk.core.Point3D.create(x1, y1, 0))
            ln.addByTwoPoints(
                adsk.core.Point3D.create(x1, y1, 0),
                adsk.core.Point3D.create(x0, y1, 0))
            ln.addByTwoPoints(
                adsk.core.Point3D.create(x0, y1, 0),
                adsk.core.Point3D.create(x0, y0, 0))

            if sk.profiles.count > 0:
                ext = extrudes.createInput(
                    sk.profiles.item(0),
                    adsk.fusion.FeatureOperations.JoinFeatureOperation)
                off = adsk.fusion.OffsetStartDefinition.create(
                    adsk.core.ValueInput.createByReal(BASE))
                ext.startExtent = off
                ext.setDistanceExtent(False,
                    adsk.core.ValueInput.createByReal(KIT_H))
                extrudes.add(ext)

        # =============================================
        # STEP 3: 4 retention clips
        # =============================================
        clips = [
            (0, -kw, 0, -1),
            (0, kw, 0, 1),
            (-kl, 0, 1, 0),
            (kl, 0, 1, 0),
        ]

        for cx, cy, is_side, sign in clips:
            sk = sketches.add(xyPlane)
            cl = sk.sketchCurves.sketchLines

            if is_side:
                sign_x = -1 if cx < 0 else 1
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx, cy - CLIP_W/2, 0),
                    adsk.core.Point3D.create(cx + sign_x * CLIP_D, cy - CLIP_W/2, 0))
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx + sign_x * CLIP_D, cy - CLIP_W/2, 0),
                    adsk.core.Point3D.create(cx + sign_x * CLIP_D, cy + CLIP_W/2, 0))
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx + sign_x * CLIP_D, cy + CLIP_W/2, 0),
                    adsk.core.Point3D.create(cx, cy + CLIP_W/2, 0))
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx, cy + CLIP_W/2, 0),
                    adsk.core.Point3D.create(cx, cy - CLIP_W/2, 0))
            else:
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx - CLIP_W/2, cy, 0),
                    adsk.core.Point3D.create(cx + CLIP_W/2, cy, 0))
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx + CLIP_W/2, cy, 0),
                    adsk.core.Point3D.create(cx + CLIP_W/2, cy + sign * CLIP_D, 0))
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx + CLIP_W/2, cy + sign * CLIP_D, 0),
                    adsk.core.Point3D.create(cx - CLIP_W/2, cy + sign * CLIP_D, 0))
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx - CLIP_W/2, cy + sign * CLIP_D, 0),
                    adsk.core.Point3D.create(cx - CLIP_W/2, cy, 0))

            if sk.profiles.count > 0:
                ext = extrudes.createInput(
                    sk.profiles.item(0),
                    adsk.fusion.FeatureOperations.JoinFeatureOperation)
                off = adsk.fusion.OffsetStartDefinition.create(
                    adsk.core.ValueInput.createByReal(BASE + KIT_H - 0.15))
                ext.startExtent = off
                ext.setDistanceExtent(False,
                    adsk.core.ValueInput.createByReal(CLIP_H))
                extrudes.add(ext)

        # =============================================
        # STEP 4: Camera lens hole
        # =============================================
        sk_lens = sketches.add(xyPlane)
        sk_lens.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0), LENS_R)
        if sk_lens.profiles.count > 0:
            ext = extrudes.createInput(
                sk_lens.profiles.item(0),
                adsk.fusion.FeatureOperations.CutFeatureOperation)
            ext.setAllExtent(
                adsk.fusion.ExtentDirections.PositiveExtentDirection)
            extrudes.add(ext)

        # =============================================
        # STEP 5: USB slot
        # =============================================
        sk_usb = sketches.add(xyPlane)
        lu = sk_usb.sketchCurves.sketchLines
        lu.addByTwoPoints(
            adsk.core.Point3D.create(kl, -USB_W/2, 0),
            adsk.core.Point3D.create(kl + WALL + margin + 0.1, -USB_W/2, 0))
        lu.addByTwoPoints(
            adsk.core.Point3D.create(kl + WALL + margin + 0.1, -USB_W/2, 0),
            adsk.core.Point3D.create(kl + WALL + margin + 0.1, USB_W/2, 0))
        lu.addByTwoPoints(
            adsk.core.Point3D.create(kl + WALL + margin + 0.1, USB_W/2, 0),
            adsk.core.Point3D.create(kl, USB_W/2, 0))
        lu.addByTwoPoints(
            adsk.core.Point3D.create(kl, USB_W/2, 0),
            adsk.core.Point3D.create(kl, -USB_W/2, 0))

        if sk_usb.profiles.count > 0:
            ext = extrudes.createInput(
                sk_usb.profiles.item(0),
                adsk.fusion.FeatureOperations.CutFeatureOperation)
            off = adsk.fusion.OffsetStartDefinition.create(
                adsk.core.ValueInput.createByReal(BASE + 0.2))
            ext.startExtent = off
            ext.setDistanceExtent(False,
                adsk.core.ValueInput.createByReal(0.5))
            extrudes.add(ext)

        # =============================================
        # STEP 6: 4 strap tabs with holes
        # =============================================
        tab_positions = [
            (kl + margin + TAB_L/2, 0, 0),
            (-(kl + margin + TAB_L/2), 0, 180),
            (0, kw + margin + TAB_L/2, 90),
            (0, -(kw + margin + TAB_L/2), 270),
        ]

        for tx, ty, angle_deg in tab_positions:
            angle = math.radians(angle_deg)
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            cos_p = math.cos(angle + math.pi/2)
            sin_p = math.sin(angle + math.pi/2)
            tw = TAB_W / 2
            tl = TAB_L / 2

            sk = sketches.add(xyPlane)
            lt = sk.sketchCurves.sketchLines
            lt.addByTwoPoints(
                adsk.core.Point3D.create(tx - tl*cos_a + tw*cos_p,
                                          ty - tl*sin_a + tw*sin_p, 0),
                adsk.core.Point3D.create(tx + tl*cos_a + tw*cos_p,
                                          ty + tl*sin_a + tw*sin_p, 0))
            lt.addByTwoPoints(
                adsk.core.Point3D.create(tx + tl*cos_a + tw*cos_p,
                                          ty + tl*sin_a + tw*sin_p, 0),
                adsk.core.Point3D.create(tx + tl*cos_a - tw*cos_p,
                                          ty + tl*sin_a - tw*sin_p, 0))
            lt.addByTwoPoints(
                adsk.core.Point3D.create(tx + tl*cos_a - tw*cos_p,
                                          ty + tl*sin_a - tw*sin_p, 0),
                adsk.core.Point3D.create(tx - tl*cos_a - tw*cos_p,
                                          ty - tl*sin_a - tw*sin_p, 0))
            lt.addByTwoPoints(
                adsk.core.Point3D.create(tx - tl*cos_a - tw*cos_p,
                                          ty - tl*sin_a - tw*sin_p, 0),
                adsk.core.Point3D.create(tx - tl*cos_a + tw*cos_p,
                                          ty - tl*sin_a + tw*sin_p, 0))

            if sk.profiles.count > 0:
                ext = extrudes.createInput(
                    sk.profiles.item(0),
                    adsk.fusion.FeatureOperations.JoinFeatureOperation)
                ext.setDistanceExtent(False,
                    adsk.core.ValueInput.createByReal(BASE + 0.1))
                extrudes.add(ext)

            # Strap hole
            sk_h = sketches.add(xyPlane)
            sk_h.sketchCurves.sketchCircles.addByCenterRadius(
                adsk.core.Point3D.create(tx, ty, 0), HOLE_R)
            if sk_h.profiles.count > 0:
                ext_h = extrudes.createInput(
                    sk_h.profiles.item(0),
                    adsk.fusion.FeatureOperations.CutFeatureOperation)
                ext_h.setAllExtent(
                    adsk.fusion.ExtentDirections.PositiveExtentDirection)
                extrudes.add(ext_h)

        # =============================================
        # Done
        # =============================================
        app.activeViewport.fit()
        ui.messageBox(
            'MINIMAL chest piece generated!\n\n'
            'What this is:\n'
            '  A tray with walls + clips to hold your TinyML kit\n'
            '  with strap tabs to attach to your chest.\n'
            '  No decorative features. Pure function.\n\n'
            'Dimensions:\n'
            '  ~86mm x 46mm x 21mm (was 120mm round, 22mm tall)\n'
            '  0.8mm base, 1mm walls\n\n'
            'Print settings:\n'
            '  Layer height: 0.2mm (or 0.28mm for speed)\n'
            '  Infill: 10%% (base is thin enough to be all perimeters)\n'
            '  Supports: none\n'
            '  Material: PLA\n'
            '  Est. filament: ~8-12g\n'
            '  Est. print time: 30-60 min',
            'Chest Piece — Minimal')

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
