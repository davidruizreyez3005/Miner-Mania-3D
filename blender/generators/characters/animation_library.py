"""Standalone worker animation library.

Builds the test mannequin as a proxy body on the shared humanoid skeleton and
lets the animate stage apply every clip of the contract. The export stage
writes ``anim_worker_library.glb`` (all clips) and one ``anim_worker_<clip>.glb``
per clip, all with identical skeleton and track paths, so the game can load a
single clip or the whole library into any worker's AnimationPlayer.
"""

from . import mannequin


def build(ctx):
    mannequin.build(ctx)
    ctx.metadata["character"]["role"] = "animation_library"
