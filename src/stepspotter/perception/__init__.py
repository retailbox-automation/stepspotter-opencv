"""OpenCV 5 perception: the deterministic first layer of the photo-evidence gate.

``inspect_evidence(evidence, reference, zones, ...) -> PerceptionReport`` runs before any
model sees a photo. Its decision blocks the photo, asks for a specific retake, or stops
the run for a person — see ``inspect.py`` for the policy, ``thresholds.py`` for every
number and where it came from, and docs/PERCEPTION.md for what was measured.

Importing this package does not import OpenCV: ``models`` is pure pydantic, because a
saved job carries perception reports and must load anywhere. The OpenCV modules are
imported where they are used.
"""

from stepspotter.perception.models import BLOCKING, PerceptionReport

__all__ = ["BLOCKING", "PerceptionReport"]
