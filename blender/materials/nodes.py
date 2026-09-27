"""Terse shader-node graph construction helpers."""

import bpy

from utilities.meshkit import PATTERN_ATTR

AO_NODE = "mm_ao_mask"
PLACEHOLDER_IMAGE = "mm_white_placeholder"


def placeholder_image():
    img = bpy.data.images.get(PLACEHOLDER_IMAGE)
    if img is None:
        img = bpy.data.images.new(PLACEHOLDER_IMAGE, 4, 4, alpha=False)
        img.generated_color = (1.0, 1.0, 1.0, 1.0)
        img.colorspace_settings.name = "Non-Color"
    return img


class NB:
    """Node builder bound to one material."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.mat = mat
        self.nt = mat.node_tree
        self.nodes = self.nt.nodes
        self.links = self.nt.links
        self.nodes.clear()
        self._x = 0
        self.out = self.new("ShaderNodeOutputMaterial")
        self.bsdf = self.new("ShaderNodeBsdfPrincipled")
        self.links.new(self.bsdf.outputs["BSDF"], self.out.inputs["Surface"])
        self._coord = None
        self._geom = None
        self._ao = None

    # -- basics ------------------------------------------------------------
    def new(self, type_name, **props):
        n = self.nodes.new(type_name)
        n.location = (self._x, 0)
        self._x -= 180
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def _set(self, sock, value):
        if isinstance(value, bpy.types.NodeSocket):
            self.links.new(value, sock)
        elif value is not None:
            if hasattr(sock, "default_value"):
                dv = sock.default_value
                if hasattr(dv, "__len__") and not isinstance(value, (tuple, list)):
                    value = [value] * len(dv)
                if hasattr(dv, "__len__") and len(value) == 3 and len(dv) == 4:
                    value = (value[0], value[1], value[2], 1.0)
                sock.default_value = value

    def coord(self, scale=1.0, offset=(0.0, 0.0, 0.0)):
        if self._coord is None:
            a = self.new("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=PATTERN_ATTR)
            self._coord = a.outputs["Vector"]
        v = self._coord
        if offset != (0.0, 0.0, 0.0):
            v = self.vmath("ADD", v, offset)
        if scale != 1.0:
            if isinstance(scale, (tuple, list)):
                v = self.vmath("MULTIPLY", v, tuple(scale))
            else:
                v = self.vmath("SCALE", v, scale=scale)
        return v

    def geometry(self):
        if self._geom is None:
            self._geom = self.new("ShaderNodeNewGeometry")
        return self._geom

    def ao_mask(self):
        """Baked ambient occlusion (white until the AO pass has run)."""
        if self._ao is None:
            n = self.new("ShaderNodeTexImage", name=AO_NODE, label=AO_NODE)
            n.image = placeholder_image()
            n.interpolation = "Linear"
            self._ao = n.outputs["Color"]
        return self._ao

    # -- math ----------------------------------------------------------------
    def math(self, op, a, b=None, clamp=False):
        n = self.new("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._set(n.inputs[0], a)
        if b is not None:
            self._set(n.inputs[1], b)
        return n.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        n = self.new("ShaderNodeVectorMath", operation=op)
        self._set(n.inputs[0], a)
        if b is not None:
            self._set(n.inputs[1], b)
        if scale is not None:
            n.inputs["Scale"].default_value = scale
        out = n.outputs["Value"] if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else n.outputs["Vector"]
        return out

    def sep(self, vec):
        n = self.new("ShaderNodeSeparateXYZ")
        self._set(n.inputs[0], vec)
        return n.outputs["X"], n.outputs["Y"], n.outputs["Z"]

    def comb(self, x, y, z):
        n = self.new("ShaderNodeCombineXYZ")
        self._set(n.inputs[0], x)
        self._set(n.inputs[1], y)
        self._set(n.inputs[2], z)
        return n.outputs[0]

    def map_range(self, value, fmin, fmax, tmin=0.0, tmax=1.0, smooth=False, clamp=True):
        n = self.new("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP" if smooth else "LINEAR", clamp=clamp)
        self._set(n.inputs["Value"], value)
        self._set(n.inputs["From Min"], fmin)
        self._set(n.inputs["From Max"], fmax)
        self._set(n.inputs["To Min"], tmin)
        self._set(n.inputs["To Max"], tmax)
        return n.outputs["Result"]

    def mix(self, fac, a, b, blend="MIX"):
        n = self.new("ShaderNodeMix", data_type="RGBA", blend_type=blend, clamp_result=True)
        self._set(n.inputs["Factor"], fac)
        self._set(n.inputs[6], a)
        self._set(n.inputs[7], b)
        return n.outputs[2]

    def mixf(self, fac, a, b):
        n = self.new("ShaderNodeMix", data_type="FLOAT")
        self._set(n.inputs["Factor"], fac)
        self._set(n.inputs[2], a)
        self._set(n.inputs[3], b)
        return n.outputs[0]

    def ramp(self, fac, stops, interpolation="LINEAR"):
        n = self.new("ShaderNodeValToRGB")
        cr = n.color_ramp
        cr.interpolation = interpolation
        els = cr.elements
        while len(els) > 1:
            els.remove(els[-1])
        for i, (pos, col) in enumerate(stops):
            e = els[0] if i == 0 else els.new(pos)
            e.position = pos
            if not isinstance(col, (tuple, list)):
                col = (col, col, col)
            e.color = (col[0], col[1], col[2], 1.0)
        self._set(n.inputs["Fac"], fac)
        return n.outputs["Color"]

    def hsv(self, color, hue=0.5, sat=1.0, val=1.0, fac=1.0):
        n = self.new("ShaderNodeHueSaturation")
        self._set(n.inputs["Hue"], hue)
        self._set(n.inputs["Saturation"], sat)
        self._set(n.inputs["Value"], val)
        self._set(n.inputs["Fac"], fac)
        self._set(n.inputs["Color"], color)
        return n.outputs["Color"]

    # -- textures -------------------------------------------------------------
    def noise(self, vec, scale=1.0, detail=2.0, roughness=0.5, distortion=0.0, ntype="FBM", lacunarity=2.0):
        n = self.new("ShaderNodeTexNoise", noise_dimensions="3D", noise_type=ntype, normalize=True)
        self._set(n.inputs["Vector"], vec)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = roughness
        n.inputs["Lacunarity"].default_value = lacunarity
        n.inputs["Distortion"].default_value = distortion
        return n.outputs["Fac"]

    def voronoi(self, vec, scale=1.0, feature="F1", randomness=1.0, output="Distance", detail=0.0):
        n = self.new("ShaderNodeTexVoronoi", voronoi_dimensions="3D", feature=feature, distance="EUCLIDEAN")
        self._set(n.inputs["Vector"], vec)
        n.inputs["Scale"].default_value = scale
        n.inputs["Randomness"].default_value = randomness
        if "Detail" in n.inputs:
            n.inputs["Detail"].default_value = detail
        return n.outputs[output]

    def wave(self, vec, scale=1.0, direction="X", profile="SIN", distortion=0.0, detail=2.0, wave_type="BANDS",
             phase=0.0, detail_scale=1.0):
        n = self.new("ShaderNodeTexWave", wave_type=wave_type, wave_profile=profile)
        if wave_type == "BANDS":
            n.bands_direction = direction
        else:
            n.rings_direction = direction if direction in ("X", "Y", "Z", "SPHERICAL") else "SPHERICAL"
        self._set(n.inputs["Vector"], vec)
        n.inputs["Scale"].default_value = scale
        n.inputs["Distortion"].default_value = distortion
        n.inputs["Detail"].default_value = detail
        n.inputs["Detail Scale"].default_value = detail_scale
        n.inputs["Phase Offset"].default_value = phase
        return n.outputs["Fac"]

    def pointiness(self):
        return self.geometry().outputs["Pointiness"]

    def up_facing(self):
        """Dot of the surface normal with world up (dust / moss masks)."""
        return self.vmath("DOT_PRODUCT", self.geometry().outputs["Normal"], (0.0, 0.0, 1.0))

    def bump(self, height, strength=0.1, distance=0.02, normal=None, invert=False):
        n = self.new("ShaderNodeBump", invert=invert)
        self._set(n.inputs["Height"], height)
        n.inputs["Strength"].default_value = strength
        n.inputs["Distance"].default_value = distance
        if normal is not None:
            self._set(n.inputs["Normal"], normal)
        return n.outputs["Normal"]

    # -- outputs -----------------------------------------------------------
    def surface(self, base=None, roughness=None, metallic=None, normal=None, alpha=None, emission=None,
                emission_strength=None, specular=0.5):
        b = self.bsdf
        self._set(b.inputs["Base Color"], base)
        self._set(b.inputs["Roughness"], roughness)
        self._set(b.inputs["Metallic"], metallic)
        if normal is not None:
            self._set(b.inputs["Normal"], normal)
        if alpha is not None:
            self._set(b.inputs["Alpha"], alpha)
        if emission is not None:
            self._set(b.inputs["Emission Color"], emission)
            self._set(b.inputs["Emission Strength"], emission_strength if emission_strength is not None else 1.0)
        self._set(b.inputs["Specular IOR Level"], specular)
