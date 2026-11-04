"""Pure session logic: no UI, network, or hardware required."""
from dataclasses import dataclass
from enum import Enum
import math
import statistics


class Stage(str, Enum):
    READY = "Ready"
    WELCOME = "Welcome"
    CALIBRATE = "Finding your baseline"
    EXPLORE = "A little imagination"
    RESPOND = "Reading the ripples"
    SETTLE = "Mixing your recipe"
    COMPLETE = "Your martini is ready"
    STOPPED = "Stopped"


SEQUENCE = (Stage.WELCOME, Stage.CALIBRATE, Stage.EXPLORE, Stage.RESPOND, Stage.SETTLE)
DURATIONS = (7, 8, 14, 10, 3)
LINES = {
    Stage.WELCOME: "Welcome to Dirty Minds. Make yourself comfortable. You can stop whenever you like.",
    Stage.CALIBRATE: "Rest your fingers on the contacts. Be still for a moment. Let's find where we begin.",
    Stage.EXPLORE: "Close your eyes, if you like. Imagine a secret you would only tell over a very good martini. Take your time.",
    Stage.SETTLE: "I think I've found your secret ingredient. A little patience. A little salt.",
}
RESPONSE_LINES = (
    "A quiet ripple. Some secrets prefer to stay close. Let's keep this one subtle.",
    "Something shifted. Let's give that thought a little more salt.",
    "Quite a ripple. This martini is asking for extra olives.",
)
FINISH_LINES = (
    "Your martini is ready. A little dirty, with a secret on the side.",
    "Your martini is ready. A classic dirty martini. Keep the thought that inspired it.",
    "Your martini is ready. Extra dirty. Some secrets come with olives.",
)
TEST_LINE = "Welcome to Dirty Minds. If you can hear me, we're ready to begin."


def clamp(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("Signal must be a finite number.")
    return min(1.0, max(0.0, value))


def band(score: float) -> int:
    return 0 if score < 0.33 else 1 if score < 0.67 else 2


@dataclass(frozen=True)
class Recipe:
    name: str
    score: float
    gin_ml: int
    vermouth_ml: int
    brine_ml: int
    olives: int

    def display(self) -> str:
        return (
            f"{self.name}\n\n"
            f"{self.gin_ml} ml gin (or vodka)\n"
            f"{self.vermouth_ml} ml dry vermouth\n"
            f"{self.brine_ml} ml olive brine\n"
            f"{self.olives} olives\n\n"
            "Stir liquids with ice until cold.\n"
            "Strain into a chilled glass. Garnish with olives.\n"
            f"Signal change: {self.score:.0%} · playful recipe mapping"
        )


def make_recipe(score: float) -> Recipe:
    score = clamp(score)
    # Only brine/garnish change; signal never increases the alcohol amount.
    brine = 5 + int(score * 4 + 0.5) * 5
    names = ("A little dirty", "Dirty Minds martini", "Extra dirty")
    return Recipe(names[band(score)], score, 50, 10, brine, 1 + band(score))


class Session:
    def __init__(self, span: float = 200, time_scale: float = 1):
        if not math.isfinite(span) or span <= 0 or time_scale <= 0:
            raise ValueError("Signal span and time scale must be positive.")
        self.span = span
        self.time_scale = time_scale
        self.stage = Stage.READY
        self.entered = 0.0
        self.smoothed = None
        self.baseline = None
        self.calibration = []
        self.responses = []
        self.signal = 0.0
        self.recipe = None

    @property
    def active(self):
        return self.stage in SEQUENCE

    @property
    def score(self):
        return statistics.fmean(self.responses) if self.responses else 0.0

    def start(self, now: float):
        self.__init__(self.span, self.time_scale)
        self.stage = Stage.WELCOME
        self.entered = now

    def stop(self):
        self.stage = Stage.STOPPED
        self.recipe = None

    def sample(self, raw: float):
        if not math.isfinite(raw):
            return
        self.smoothed = raw if self.smoothed is None else 0.22 * raw + 0.78 * self.smoothed
        if self.stage == Stage.CALIBRATE:
            self.calibration.append(self.smoothed)
        if self.baseline is not None:
            self.signal = clamp(abs(self.smoothed - self.baseline) / self.span)
            if self.stage in (Stage.EXPLORE, Stage.RESPOND):
                self.responses.append(self.signal)

    def tick(self, now: float, voice_busy: bool = False):
        if not self.active:
            return False
        index = SEQUENCE.index(self.stage)
        if voice_busy or now - self.entered < DURATIONS[index] * self.time_scale:
            return False
        if self.stage == Stage.CALIBRATE:
            if len(self.calibration) < 10:
                raise ValueError("Not enough sensor readings to calibrate. Check the input and start again.")
            self.baseline = statistics.median(self.calibration)
        if index == len(SEQUENCE) - 1:
            if len(self.responses) < 10:
                raise ValueError("Not enough sensor readings for a recipe. Check the input and start again.")
            self.recipe = make_recipe(self.score)
            self.stage = Stage.COMPLETE
        else:
            self.stage = SEQUENCE[index + 1]
        self.entered = now
        return True

    def progress(self, now: float):
        if self.stage == Stage.COMPLETE:
            return 100.0
        if not self.active:
            return 0.0
        index = SEQUENCE.index(self.stage)
        elapsed = min(DURATIONS[index], max(0, now - self.entered) / self.time_scale)
        return 100 * (sum(DURATIONS[:index]) + elapsed) / sum(DURATIONS)

    def line(self):
        if self.stage == Stage.RESPOND:
            return RESPONSE_LINES[band(self.score)]
        if self.stage == Stage.COMPLETE:
            return FINISH_LINES[band(self.score)]
        return LINES.get(self.stage, "")

