"""Four temptations, independent signal scores, and a bounded brine recipe."""
from dataclasses import asdict, dataclass
from enum import Enum
import math
import statistics


@dataclass(frozen=True)
class Ingredient:
    key: str
    name: str
    pump: int
    voice_id: str
    voice_name: str
    character: str
    pitch: str

    @property
    def introduction(self):
        return f"My name is {self.character}."


INGREDIENTS = (
    Ingredient("onion", "Silver onion", 1, "1ykC5GeLM4dP82qkyo91", "Nora", "Pearl",
        "A silver onion with layers. Take one sip and I'll tell you a secret. "
        "Sweet at first, then a little sharp. I never said it was a nice secret."),
    Ingredient("olive", "Classic olive", 2, "PB6BdkFkZLbI39GHdnbQ", "Natasha", "Olive Twist",
        "Of course I want some more. More velvet salt, more ice, and a little less innocence. "
        "Your martini wore white. How very optimistic."),
    Ingredient("jalapeno", "Jalapeño", 3, "A6TsrDqI2qlO9AWAfZHY", "Shanni", "Pepper",
        "Your glass is freezing. Lucky for you, I brought a spark. "
        "First comes a crisp little bite. Then the kind of heat that stays for another sip."),
    Ingredient("pickle", "Dutch augurk", 4, "1cxc5c3E9K6F1wlqOJGV", "Emily", "Dill With It",
        "A proper Dutch augurk. Crisp, cool, and a terrible influence on an innocent martini. "
        "You call it trouble. I call it lekker."),
)


class Stage(str, Enum):
    READY = "Ready"
    WELCOME = "A dirty little introduction"
    BASELINE_PROMPT = "Your baseline dirty"
    CALIBRATE = "Finding your baseline · keep still"
    ROUND_1 = "1 / 4 · Silver onion"
    REST_1 = "A quiet breath"
    ROUND_2 = "2 / 4 · Classic olive"
    REST_2 = "A little pause"
    ROUND_3 = "3 / 4 · Jalapeño"
    REST_3 = "Let the heat settle"
    ROUND_4 = "4 / 4 · Dutch augurk"
    REVEAL = "Your dirty mind, your blend"
    DISPENSE = "Making it dirty"
    FAREWELL = "You deserve a dirty drink"
    COMPLETE = "Your session is complete"
    STOPPED = "Stopped"


SEQUENCE = tuple(s for s in Stage if s not in (Stage.READY, Stage.COMPLETE, Stage.STOPPED))
ROUND_STAGES = (Stage.ROUND_1, Stage.ROUND_2, Stage.ROUND_3, Stage.ROUND_4)
REST_STAGES = (Stage.REST_1, Stage.REST_2, Stage.REST_3)
LINES = {
    Stage.WELCOME: "Hello, dirty mind. Four pickles walked into a bar. "
        "One of them is about to get into your martini. "
        "Close your eyes if you like. Let's see what kind of dirty you take yours. "
        "You can stop whenever you like.",
    Stage.BASELINE_PROMPT: "First, I need to sense your baseline dirty. Rest your fingers on the contacts. "
        "Stay still for a moment. Just you, me, and a little anticipation.",
    Stage.REVEAL: "The votes are in. The brine has spoken. "
        "Your very own dirty blend is ready. Let's make it.",
    Stage.FAREWELL: "Thank you for sharing your dirty mind. You deserve a dirty drink. "
        "Take your secret with you. Leave the glass with us.",
    **{stage: f"{ingredient.introduction} {ingredient.pitch}" for stage, ingredient in zip(ROUND_STAGES, INGREDIENTS)},
}
VOICE_CUES = {Stage.WELCOME: "[exhales]", **{
    stage: cue for stage, cue in zip(ROUND_STAGES, ("[exhales]", "[sighs]", "[exhales]", "[sighs]"))
}}
TEST_LINE = "Welcome to Dirty Minds. If you can hear me, we're ready to begin."
AFTER_SPEECH = {stage: 6 if stage in ROUND_STAGES else 8 if stage == Stage.CALIBRATE
                else 4 if stage in REST_STAGES else 1 for stage in SEQUENCE}


def clamp(value):
    if not math.isfinite(value):
        raise ValueError("Signal must be a finite number.")
    return min(1.0, max(0.0, value))


@dataclass(frozen=True)
class RoundResult:
    ingredient: str
    score: float
    peak: float
    samples: int


@dataclass(frozen=True)
class Recipe:
    name: str
    amounts: tuple
    reason: str
    gin_ml: int = 50
    vermouth_ml: int = 10

    @property
    def brine_ml(self):
        return sum(self.amounts)

    def display(self):
        brines = ", ".join(f"{ml:g} ml {item.name.lower()} brine"
                           for item, ml in zip(INGREDIENTS, self.amounts) if ml)
        return (f"{self.name}\n50 ml gin (or vodka) + 10 ml dry vermouth\n{brines}\n"
                "Stir with ice, strain cold, garnish to match.\n" + self.reason)


def make_recipe(scores):
    if len(scores) != 4:
        raise ValueError("A recipe needs all four round scores.")
    scores = [clamp(value) for value in scores]
    rank = sorted(range(4), key=lambda i: (-scores[i], (1, 0, 2, 3)[i]))
    first, second = rank[:2]
    amounts = [0.0] * 4
    if scores[first] < 0.10:
        amounts[1] = 15.0
        name, reason = "The quiet classic", "Small responses: classic olive is the fallback."
    elif scores[second] + 1e-12 >= scores[first] * 0.75:
        amounts[first] = round(15 * scores[first] / (scores[first] + scores[second]), 1)
        amounts[second] = round(15 - amounts[first], 1)
        name = f"{INGREDIENTS[first].name} & {INGREDIENTS[second].name.lower()} affair"
        reason = "A close second joins the strongest response in a 15 ml blend."
    else:
        amounts[first] = 15.0
        name = f"A little {INGREDIENTS[first].name.lower()} trouble"
        reason = "The strongest response chooses all 15 ml of brine."
    return Recipe(name, tuple(amounts), reason)


class Session:
    def __init__(self, span=200, time_scale=1):
        if not all(math.isfinite(x) and x > 0 for x in (span, time_scale)):
            raise ValueError("Signal span and time scale must be positive.")
        self.span, self.time_scale = span, time_scale
        self.stage, self.entered = Stage.READY, 0.0
        self.smoothed = self.baseline = self.recipe = None
        self.calibration, self.responses, self.results = [], [], []
        self.signal = 0.0
        self.spoken = self.voice_pending = self.playback_has_started = False
        self.ready_at = None
        self.delivery_complete = False

    @property
    def active(self):
        return self.stage in SEQUENCE

    @property
    def round_index(self):
        return ROUND_STAGES.index(self.stage) if self.stage in ROUND_STAGES else None

    @property
    def collecting(self):
        return self.round_index is not None and self.playback_has_started

    @property
    def needs_sensor(self):
        return self.active and SEQUENCE.index(self.stage) <= SEQUENCE.index(Stage.ROUND_4)

    def _enter(self, stage, now):
        self.stage, self.entered = stage, now
        self.voice_pending = self.spoken and bool(LINES.get(stage))
        self.playback_has_started = not self.voice_pending
        self.responses = []
        duration = AFTER_SPEECH.get(stage, 0)
        if not self.spoken and stage in LINES:
            duration += 14 if stage in ROUND_STAGES else 4
        self.ready_at = None if self.voice_pending or stage == Stage.DISPENSE else now + duration * self.time_scale

    def start(self, now, *, spoken=False):
        self.__init__(self.span, self.time_scale)
        self.spoken = spoken
        self._enter(Stage.WELCOME, now)

    def playback_started(self):
        if self.voice_pending:
            self.playback_has_started = True

    def voice_finished(self, now):
        if self.voice_pending:
            self.voice_pending = False
            self.ready_at = now + AFTER_SPEECH[self.stage] * self.time_scale

    def stop(self):
        self.stage = Stage.STOPPED
        self.voice_pending = False

    def sample(self, raw):
        if not math.isfinite(raw):
            return
        self.smoothed = raw if self.smoothed is None else 0.22 * raw + 0.78 * self.smoothed
        if self.stage == Stage.CALIBRATE:
            self.calibration.append(self.smoothed)
        if self.baseline is not None:
            self.signal = clamp(abs(self.smoothed - self.baseline) / self.span)
            if self.collecting:
                self.responses.append(self.signal)

    def tick(self, now, voice_busy=False):
        if not self.active or self.stage == Stage.DISPENSE or self.voice_pending or voice_busy:
            return False
        if self.ready_at is None or now < self.ready_at:
            return False
        if self.stage == Stage.CALIBRATE:
            if len(self.calibration) < 10:
                raise ValueError("Not enough sensor readings for a baseline. Check the input and start again.")
            self.baseline = statistics.median(self.calibration)
        index = self.round_index
        if index is not None:
            if len(self.responses) < 10:
                raise ValueError(f"Not enough sensor readings for round {index + 1}. Start a fresh session.")
            self.results.append(RoundResult(INGREDIENTS[index].key, statistics.fmean(self.responses),
                                            max(self.responses), len(self.responses)))
            if index == 3:
                self.recipe = make_recipe([result.score for result in self.results])
        position = SEQUENCE.index(self.stage) + 1
        if self.stage == Stage.REVEAL and self.delivery_complete:
            position += 1  # Delivery finished during the reveal, so go straight to farewell.
        self._enter(SEQUENCE[position] if position < len(SEQUENCE) else Stage.COMPLETE, now)
        return True

    def finish_delivery(self, now):
        if self.stage == Stage.REVEAL:
            self.delivery_complete = True
            return False
        if self.stage != Stage.DISPENSE:
            return False
        self.delivery_complete = True
        self._enter(Stage.FAREWELL, now)
        return True

    def progress(self, now):
        if self.stage == Stage.COMPLETE:
            return 100.0
        if not self.active:
            return 0.0
        fraction = 0 if self.ready_at is None else min(1, max(0, (now - self.entered) / max(.001, self.ready_at - self.entered)))
        return 100 * (SEQUENCE.index(self.stage) + fraction) / len(SEQUENCE)

    def line(self):
        return LINES.get(self.stage, "Keep still. Let the last little ripple settle." if self.stage in REST_STAGES
                         else "Stay still while we find your baseline." if self.stage == Stage.CALIBRATE else "")

    def record(self):
        return {"stage": self.stage.value, "baseline": self.baseline, "gsr_span": self.span,
                "rounds": [asdict(result) for result in self.results],
                "recipe": asdict(self.recipe) if self.recipe else None,
                "delivery_complete": self.delivery_complete,
                "measurement": "Artistic signal mapping; not a measure of thoughts or desire."}
