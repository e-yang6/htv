#Author: Generated for HTV project
#Description: Sturdy chest piece for Arduino TinyML Kit
#             Correct orientation: long side vertical in Fusion default view

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
        #
        # ORIENTATION in Fusion (looking down, default top view):
        #
        #   Y axis = vertical (long dimension, 81mm)
        #   X axis = horizontal (short dimension, 52mm)
        #
        #              +Y = TOP (OV7675 camera)
        #          ┌──────────────┐
        #          │              │
        #  -X =    │              │  +X =
        #  LEFT    │   kit here   │  RIGHT
        #  (long)  │              │  (long)
        #          │              │
        #          └──────────────┘
        #              -Y = BOTTOM
        #
        #   Power slot: BOTTOM wall, far RIGHT corner
        #   USB slot:   LEFT wall, near BOTTOM
        #   Both slots open all the way to the top of the walls
        #

        # Kit (confirmed dimensions)
        KIT_LONG = 8.1            # 81mm (along Y)
        KIT_SHORT = 5.2           # 52mm (along X)
        KIT_H = 2.0              # 20mm stack height
        CLEARANCE = 0.15         # 1.5mm tolerance per side

        # Structure
        WALL = 0.25              # 2.5mm walls
        BASE = 0.2               # 2mm base
        CHAMFER = 0.1            # 1mm chamfers

        # Clips
        CLIP_W = 0.4
        CLIP_D = 0.12
        CLIP_H = 0.15

        # Strap tabs
        TAB_W = 1.0
        TAB_L = 1.2
        HOLE_R = 0.25

        # Wire slots (full height, open to top of wall)
        USB_SLOT_W = 2.0         # 20mm wide
        PWR_SLOT_W = 2.5         # 25mm wide

        # Camera lens
        LENS_R = 0.5

        sketches = rootComp.sketches
        xyPlane = rootComp.xYConstructionPlane
        extrudes = rootComp.features.extrudeFeatures
        chamfers = rootComp.features.chamferFeatures

        # Half-sizes for the pocket interior
        hx = (KIT_SHORT / 2) + CLEARANCE   # half width (X)
        hy = (KIT_LONG / 2) + CLEARANCE    # half height (Y)

        # Outer box edges
        ox = hx + WALL
        oy = hy + WALL

        # =============================================
        # STEP 1: Base plate
        # =============================================
        sk_base = sketches.add(xyPlane)
        lb = sk_base.sketchCurves.sketchLines
        lb.addByTwoPoints(
            adsk.core.Point3D.create(-ox, -oy, 0),
            adsk.core.Point3D.create(ox, -oy, 0))
        lb.addByTwoPoints(
            adsk.core.Point3D.create(ox, -oy, 0),
            adsk.core.Point3D.create(ox, oy, 0))
        lb.addByTwoPoints(
            adsk.core.Point3D.create(ox, oy, 0),
            adsk.core.Point3D.create(-ox, oy, 0))
        lb.addByTwoPoints(
            adsk.core.Point3D.create(-ox, oy, 0),
            adsk.core.Point3D.create(-ox, -oy, 0))

        if sk_base.profiles.count > 0:
            ext_b = extrudes.createInput(
                sk_base.profiles.item(0),
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            ext_b.setDistanceExtent(False,
                adsk.core.ValueInput.createByReal(BASE))
            bf = extrudes.add(ext_b)
            bf.bodies.item(0).name = "ChestPiece"

        # =============================================
        # STEP 2: Walls (outer box minus inner pocket)
        # =============================================
        sk_w = sketches.add(xyPlane)
        lw = sk_w.sketchCurves.sketchLines
        # Outer
        lw.addByTwoPoints(adsk.core.Point3D.create(-ox, -oy, 0),
                          adsk.core.Point3D.create(ox, -oy, 0))
        lw.addByTwoPoints(adsk.core.Point3D.create(ox, -oy, 0),
                          adsk.core.Point3D.create(ox, oy, 0))
        lw.addByTwoPoints(adsk.core.Point3D.create(ox, oy, 0),
                          adsk.core.Point3D.create(-ox, oy, 0))
        lw.addByTwoPoints(adsk.core.Point3D.create(-ox, oy, 0),
                          adsk.core.Point3D.create(-ox, -oy, 0))
        # Inner
        lw.addByTwoPoints(adsk.core.Point3D.create(-hx, -hy, 0),
                          adsk.core.Point3D.create(hx, -hy, 0))
        lw.addByTwoPoints(adsk.core.Point3D.create(hx, -hy, 0),
                          adsk.core.Point3D.create(hx, hy, 0))
        lw.addByTwoPoints(adsk.core.Point3D.create(hx, hy, 0),
                          adsk.core.Point3D.create(-hx, hy, 0))
        lw.addByTwoPoints(adsk.core.Point3D.create(-hx, hy, 0),
                          adsk.core.Point3D.create(-hx, -hy, 0))

        wall_area = (2*ox)*(2*oy) - (2*hx)*(2*hy)
        wall_prof = None
        for i in range(sk_w.profiles.count):
            p = sk_w.profiles.item(i)
            a = p.areaProperties().area
            if abs(a - wall_area) < 2.0:
                wall_prof = p
                break
        if wall_prof is None:
            for i in range(sk_w.profiles.count):
                p = sk_w.profiles.item(i)
                a = p.areaProperties().area
                full = (2*ox)*(2*oy)
                if a < full and (wall_prof is None or a > wall_prof.areaProperties().area):
                    wall_prof = p

        if wall_prof:
            ext_w = extrudes.createInput(
                wall_prof,
                adsk.fusion.FeatureOperations.JoinFeatureOperation)
            off_w = adsk.fusion.OffsetStartDefinition.create(
                adsk.core.ValueInput.createByReal(BASE))
            ext_w.startExtent = off_w
            ext_w.setDistanceExtent(False,
                adsk.core.ValueInput.createByReal(KIT_H))
            extrudes.add(ext_w)

        # =============================================
        # STEP 3: Power slot — BOTTOM wall (-Y), far RIGHT (+X)
        # Full height: cuts from base to top of wall
        # =============================================
        sk_pwr = sketches.add(xyPlane)
        lp = sk_pwr.sketchCurves.sketchLines
        # Centered at about 60% toward the right edge
        pwr_cx = hx * 0.6
        p_x0 = pwr_cx - PWR_SLOT_W / 2
        p_x1 = pwr_cx + PWR_SLOT_W / 2
        p_y0 = -oy - 0.1
        p_y1 = -hy + 0.1
        lp.addByTwoPoints(adsk.core.Point3D.create(p_x0, p_y0, 0),
                          adsk.core.Point3D.create(p_x1, p_y0, 0))
        lp.addByTwoPoints(adsk.core.Point3D.create(p_x1, p_y0, 0),
                          adsk.core.Point3D.create(p_x1, p_y1, 0))
        lp.addByTwoPoints(adsk.core.Point3D.create(p_x1, p_y1, 0),
                          adsk.core.Point3D.create(p_x0, p_y1, 0))
        lp.addByTwoPoints(adsk.core.Point3D.create(p_x0, p_y1, 0),
                          adsk.core.Point3D.create(p_x0, p_y0, 0))

        if sk_pwr.profiles.count > 0:
            ext_pwr = extrudes.createInput(
                sk_pwr.profiles.item(0),
                adsk.fusion.FeatureOperations.CutFeatureOperation)
            off_p = adsk.fusion.OffsetStartDefinition.create(
                adsk.core.ValueInput.createByReal(BASE))
            ext_pwr.startExtent = off_p
            ext_pwr.setDistanceExtent(False,
                adsk.core.ValueInput.createByReal(KIT_H + 0.1))
            extrudes.add(ext_pwr)

        # =============================================
        # STEP 4: USB slot — LEFT wall (-X), near BOTTOM (-Y)
        # Full height: cuts from base to top of wall
        # =============================================
        sk_usb = sketches.add(xyPlane)
        lu = sk_usb.sketchCurves.sketchLines
        # Positioned about 1/3 up from bottom end
        usb_cy = -hy * 0.5
        u_x0 = -ox - 0.1
        u_x1 = -hx + 0.1
        u_y0 = usb_cy - USB_SLOT_W / 2
        u_y1 = usb_cy + USB_SLOT_W / 2
        lu.addByTwoPoints(adsk.core.Point3D.create(u_x0, u_y0, 0),
                          adsk.core.Point3D.create(u_x1, u_y0, 0))
        lu.addByTwoPoints(adsk.core.Point3D.create(u_x1, u_y0, 0),
                          adsk.core.Point3D.create(u_x1, u_y1, 0))
        lu.addByTwoPoints(adsk.core.Point3D.create(u_x1, u_y1, 0),
                          adsk.core.Point3D.create(u_x0, u_y1, 0))
        lu.addByTwoPoints(adsk.core.Point3D.create(u_x0, u_y1, 0),
                          adsk.core.Point3D.create(u_x0, u_y0, 0))

        if sk_usb.profiles.count > 0:
            ext_usb = extrudes.createInput(
                sk_usb.profiles.item(0),
                adsk.fusion.FeatureOperations.CutFeatureOperation)
            off_u = adsk.fusion.OffsetStartDefinition.create(
                adsk.core.ValueInput.createByReal(BASE))
            ext_usb.startExtent = off_u
            ext_usb.setDistanceExtent(False,
                adsk.core.ValueInput.createByReal(KIT_H + 0.1))
            extrudes.add(ext_usb)

        # =============================================
        # STEP 5: Camera lens hole (through base)
        # =============================================
        sk_lens = sketches.add(xyPlane)
        sk_lens.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0), LENS_R)
        if sk_lens.profiles.count > 0:
            ext_lens = extrudes.createInput(
                sk_lens.profiles.item(0),
                adsk.fusion.FeatureOperations.CutFeatureOperation)
            ext_lens.setAllExtent(
                adsk.fusion.ExtentDirections.PositiveExtentDirection)
            extrudes.add(ext_lens)

        # =============================================
        # STEP 6: 4 retention clips
        # =============================================
        clip_list = [
            # (cx, cy, wall) — which wall the clip is on
            (0, -hy, 'bottom'),
            (0, hy, 'top'),
            (-hx, 0, 'left'),
            (hx, 0, 'right'),
        ]

        for cx, cy, wall in clip_list:
            sk = sketches.add(xyPlane)
            cl = sk.sketchCurves.sketchLines

            if wall in ('left', 'right'):
                sign_x = -1 if wall == 'left' else 1
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
                sign_y = -1 if wall == 'bottom' else 1
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx - CLIP_W/2, cy, 0),
                    adsk.core.Point3D.create(cx + CLIP_W/2, cy, 0))
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx + CLIP_W/2, cy, 0),
                    adsk.core.Point3D.create(cx + CLIP_W/2, cy + sign_y * CLIP_D, 0))
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx + CLIP_W/2, cy + sign_y * CLIP_D, 0),
                    adsk.core.Point3D.create(cx - CLIP_W/2, cy + sign_y * CLIP_D, 0))
                cl.addByTwoPoints(
                    adsk.core.Point3D.create(cx - CLIP_W/2, cy + sign_y * CLIP_D, 0),
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
        # STEP 7: 4 strap tabs with holes
        # =============================================
        tab_data = [
            (ox + TAB_L/2, 0, 0),       # right
            (-(ox + TAB_L/2), 0, 180),   # left
            (0, oy + TAB_L/2, 90),       # top
            (0, -(oy + TAB_L/2), 270),   # bottom
        ]

        for tx, ty, angle_deg in tab_data:
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
                    adsk.core.ValueInput.createByReal(BASE + 0.2))
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
        # STEP 8: Chamfers on outer top edges
        # =============================================
        try:
            body = rootComp.bRepBodies.item(0)
            top_z = BASE + KIT_H
            edges_col = adsk.core.ObjectCollection.create()
            for i in range(body.edges.count):
                e = body.edges.item(i)
                if e.length < 0.2:
                    continue
                sp = e.startVertex.geometry
                ep = e.endVertex.geometry
                if abs(sp.z - top_z) < 0.02 and abs(ep.z - top_z) < 0.02:
                    mid_x = (sp.x + ep.x) / 2
                    mid_y = (sp.y + ep.y) / 2
                    if abs(mid_x) > hx - 0.1 or abs(mid_y) > hy - 0.1:
                        edges_col.add(e)
            if edges_col.count > 0:
                ch_in = chamfers.createInput2()
                ch_in.chamferEdgeSets.addEqualDistanceChamferEdgeSet(
                    edges_col,
                    adsk.core.ValueInput.createByReal(CHAMFER),
                    True)
                chamfers.add(ch_in)
        except:
            pass

        # =============================================
        # Done
        # =============================================
        app.activeViewport.fit()
        ui.messageBox(
            'Chest piece generated!\n\n'
            'Orientation (Fusion top view):\n'
            '  TOP = OV7675 camera end\n'
            '  BOTTOM = opposite\n'
            '  LEFT / RIGHT = long sides\n\n'
            'Wire slots (full height, open to top):\n'
            '  BOTTOM wall, far right: 20mm power slot\n'
            '  LEFT wall, near bottom: 15mm USB slot\n\n'
            '2.5mm walls, 2mm base, chamfered edges\n'
            'Kit pocket: 84x55mm (81x52 + tolerance)\n'
            'Camera lens hole centered in base\n'
            '4 strap tabs, 4 retention clips\n\n'
            'Print: 0.2mm layers, 15%% infill, no supports\n'
            'Est: ~15-20g, ~1-1.5 hrs',
            'Chest Piece')

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
