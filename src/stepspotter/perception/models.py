"""The typed reports the perception layer returns. Pure pydantic, no OpenCV import.

``JobState`` stores ``PerceptionReport`` per step, so this module must load wherever a
job loads — including code paths that never touch an image. Keep cv2 and numpy out.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal[
    "ok",  # nothing OpenCV can see is wrong; the photo goes on to the model
    "retake",  # the photo cannot be judged as taken: blur, dark, glare, framing
    "wrong_place",  # it does not show the place this step's zones were drawn on
    "replay",  # it is a photo this job has already seen
    "no_change",  # the step had to change something, and nothing changed there
    "touched_avoid",  # something changed where the step said not to touch
    "skipped",  # OpenCV could not read the photo; nothing was decided here
]

#: Decisions that stop the photo before the model is asked.
BLOCKING: frozenset[str] = frozenset(
    {"retake", "wrong_place", "replay", "no_change", "touched_avoid"}
)

#: Decisions that a stuck person may be let past after repeated blocks
#: (see inspect.STUCK_POLICY). A replay is never one of them: a new photo always
#: clears it. touched_avoid is never one either: it already goes to a person.
OVERRIDABLE: frozenset[str] = frozenset({"retake", "wrong_place", "no_change"})


class QualityReport(BaseModel):
    """Can this photo be judged at all, before anyone asks what is in it?"""

    ok: bool
    issues: list[str] = Field(default_factory=list, description="reason codes, worst first")
    instruction: str | None = None
    width: int = 0
    height: int = 0
    sharpness_p90: float = 0.0
    sharpness_ratio: float | None = Field(
        default=None, description="evidence / reference sharpness, set only after a scene match"
    )
    mean: float = 0.0
    std: float = 0.0
    dark_frac: float = 0.0
    bright_frac: float = 0.0
    glare_blob_frac: float = 0.0
    glare_zone_frac: float | None = None


class SceneMatch(BaseModel):
    """Is the evidence the same place as the reference this step's zones live on?"""

    status: Literal["matched", "not_matched", "no_reference"]
    method: Literal["whole_frame", "zone_crop", "none"] = "none"
    good: int = 0
    inliers: int = 0
    inlier_ratio: float = 0.0
    scale: float | None = None
    overlap: float | None = None
    side_ratio: float | None = None
    rejected_because: str | None = None
    H: list[list[float]] | None = Field(
        default=None, description="evidence -> reference, in reference working pixels"
    )
    ref_size: tuple[int, int] | None = Field(default=None, description="(w, h) working px")
    ev_size: tuple[int, int] | None = None


class ReplayReport(BaseModel):
    """Was this photo already submitted in this job?"""

    replay: bool
    of: str | None = Field(default=None, description="which earlier photo it repeats")
    corner_shift: float | None = None
    scale: float | None = None
    mad: float | None = None
    changed_frac: float | None = None
    compared: int = 0


class ZoneChange(BaseModel):
    label: str
    kind: str
    changed_frac: float
    visible_frac: float


class ChangeReport(BaseModel):
    """What changed between the baseline and the evidence, zone by zone."""

    status: Literal["measured", "unreliable", "not_applicable"]
    baseline: str = Field(default="reference", description="reference, or which earlier evidence")
    act: list[ZoneChange] = Field(default_factory=list)
    avoid: list[ZoneChange] = Field(default_factory=list)
    outside_frac: float | None = Field(default=None, description="the noise floor")
    act_changed: bool | None = None
    avoid_touched: bool | None = None
    note: str | None = None


class PrivacyReport(BaseModel):
    """Faces in the frame. ``faces_checked`` is False unless a detector actually ran."""

    faces_checked: bool = False
    faces_blurred: int = 0
    model: str | None = None
    note: str | None = None


class PerceptionReport(BaseModel):
    """Everything OpenCV decided about one evidence photo, and why, and how fast."""

    decision: Decision
    reason_code: str
    reason: str
    instruction: str | None = Field(
        default=None, description="one thing a person can do to fix it; None when ok"
    )
    step_id: int | None = None
    expects_change: bool | None = None
    quality: QualityReport | None = None
    scene: SceneMatch | None = None
    replay: ReplayReport | None = None
    change: ChangeReport | None = None
    privacy: PrivacyReport = Field(default_factory=PrivacyReport)
    thresholds: dict[str, float | int | str] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(
        default_factory=dict, description="rendered images: match, heatmap, quality"
    )
    overridden: bool = Field(
        default=False,
        description="a blocking decision let through to the model by the stuck rule",
    )
    opencv: str = ""

    @property
    def blocks(self) -> bool:
        """Does this report stop the photo before the model? Overridden ones do not."""
        return self.decision in BLOCKING and not self.overridden

    @property
    def needs_human(self) -> bool:
        return self.decision == "touched_avoid"

    @property
    def ms_total(self) -> float:
        return float(self.timings_ms.get("total", 0.0))

    def brief(self) -> str:
        """One line for a tool result or a log."""
        tail = f" {self.instruction}" if self.instruction and self.blocks else ""
        return f"[OpenCV: {self.decision}] {self.reason}{tail}"


class Keyframe(BaseModel):
    """One frame picked out of a video, with why it was picked."""

    index: int
    time_s: float
    score: float
    sharpness_p90: float
    exposure_ok: bool
    inliers: int | None = None
    path: str | None = None
