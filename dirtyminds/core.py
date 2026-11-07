"""Three diagnostic stimuli, independent signal scores, and a bounded brine recipe."""
from dataclasses import asdict, dataclass
from enum import Enum
import math
import statistics


@dataclass(frozen=True)
class Ingredient:
    key: str
    name: str
    voice_id: str
    voice_name: str
    character: str
    pitch: str


INGREDIENTS = (
    Ingredient("onion", "Pickled Onion", "sP3q7DZvU8X3maXCONzw", "Kim · Dutch English",
        "Dutch-accented English. Awkwardly intimate, earnest and vulnerable. "
        "Use layers, secrets or a confession that gets a little too personal.",
        "Come a little closer. My juice is already slipping through the tube. "
        "Sweet at first. Then the pump gives it one slow pulse. "
        "That little sharp finish? I was hoping you would ask for more."),
    Ingredient("olive", "Olive", "qMeZLxL57iwdz7D3XC3e", "Trevor · British",
        "Masculine British English. Sophisticated, charming and emotionally unavailable. "
        "Use dry understatement, elegant double meanings and impeccable manners.",
        "Do leave a little room in your glass. "
        "My juice takes the scenic route through the line. "
        "One slow pulse brings a silky, salty finish. "
        "A second would be our little indiscretion."),
    Ingredient("jalapeno", "Jalapeño", "ZwLTvq6uCfb4W00YFl7F", "Ernesto · Mexican-American",
        "Mexican-accented English. Bold, playful and provocative. "
        "Tease with a dare that escalates from a small spark to lingering heat.",
        "Wait for my juice to reach the pump. Hear that little pulse? "
        "The first drop is bright. The next brings heat. "
        "Try a sip. Tell me when it stops lingering."),
)


INGREDIENT_BY_KEY = {item.key: item for item in INGREDIENTS}
DEFAULT_PUMP_ORDER = ("olive", "jalapeno", "onion")
LEGACY_PUMP_ORDER = tuple(INGREDIENT_BY_KEY)


PROFESSOR_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"


class Stage(str, Enum):
    READY = "Awaiting patient"
    WELCOME = "Patient intake"
    BASELINE_PROMPT = "Baseline instructions"
    CALIBRATE = "Baseline reading · keep still"
    ROUND_1 = "1 / 3 · The Pickled Onion"
    REST_1 = "Observation interval"
    ROUND_2 = "2 / 3 · The Olive"
    REST_2 = "Observation interval continued"
    ROUND_3 = "3 / 3 · The Jalapeño"
    REST_3 = "Final observation interval"
    REVEAL = "Assessing responses"
    DISPENSE = "Preparing your prescription"
    FAREWELL = "Discharge instructions"
    COMPLETE = "Appointment complete"
    STOPPED = "Stopped"


SEQUENCE = tuple(s for s in Stage if s not in (Stage.READY, Stage.COMPLETE, Stage.STOPPED))
ROUND_STAGES = (Stage.ROUND_1, Stage.ROUND_2, Stage.ROUND_3)
REST_STAGES = (Stage.REST_1, Stage.REST_2, Stage.REST_3)
PROFESSOR_PROTOCOL = (
    "Next, you will hear three voices. We will test what type of dirty you are. "
    "You may stop the procedure at any time."
)
LINES = {
    Stage.WELCOME: "I am the professor on duty at the Department of Inappropriate Responses. "
        "Today's study is double-blind, lightly stirred, and subject to peer re-pour. " + PROFESSOR_PROTOCOL,
    Stage.BASELINE_PROMPT: "Relax and keep still for a moment. We will take a quiet baseline.",
    Stage.REVEAL: "We have assessed your responses. Please wait while we prepare your prescription.",
    Stage.FAREWELL: "Thank you. Please keep responding inappropriately.",
    **{stage: ingredient.pitch for stage, ingredient in zip(ROUND_STAGES, INGREDIENTS)},
}
VOICE_CUES = {
    Stage.ROUND_1: ("[inhales softly]", "[sighs]"),
    Stage.ROUND_2: ("[exhales]", "[sighs softly]"),
    Stage.ROUND_3: ("[inhales slowly]", "[exhales]"),
}
WAITING_TUNE = "prescription-wait.wav"
SOUND_CUES = {Stage.WELCOME: "intake-jingle.wav", **dict.fromkeys(ROUND_STAGES, "test-ready.wav")}
TEST_LINE = "This is the professor on duty. If you can hear me, the equipment has met our modest expectations."
AFTER_SPEECH = {stage: 6 if stage in ROUND_STAGES else 8 if stage == Stage.CALIBRATE
                else 2 if stage in REST_STAGES else 1 for stage in SEQUENCE}


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
        brines = ", ".join(f"{ml:.2f} ml {item.name.lower()} brine ({ml / self.brine_ml:.1%})"
                           for item, ml in zip(INGREDIENTS, self.amounts) if ml)
        return (f"{self.name}\n50 ml gin (or vodka) + 10 ml dry vermouth\n{brines}\n"
                "Stir with ice, strain cold, garnish to match.\n" + self.reason)


def make_recipe(scores):
    if len(scores) != len(INGREDIENTS):
        raise ValueError("A prescription needs all three round scores.")
    scores = [clamp(value) for value in scores]
    total = math.fsum(scores)
    if not total:
        return Recipe("The Control Group", (5.0, 5.0, 5.0),
                      "With no measured change, the three brines share 15 ml equally.")
    house_names = ("The Layered Affair", "A Matter of Brine", "The Heat Hypothesis")
    strongest = max(range(len(scores)), key=scores.__getitem__)
    amounts = tuple(15.0 * (score / total) for score in scores)
    return Recipe(house_names[strongest], amounts,
                  "The three response scores determine the shares of 15 ml of brine.")


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
        return self.active and SEQUENCE.index(self.stage) <= SEQUENCE.index(ROUND_STAGES[-1])

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
            if self.stage == ROUND_STAGES[-1]:
                self.recipe = make_recipe([result.score for result in self.results])
        position = SEQUENCE.index(self.stage) + 1
        if self.stage == Stage.REVEAL and self.delivery_complete:
            position += 1  # Delivery already finished during the reveal.
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
        if self.stage == Stage.FAREWELL and self.recipe:
            return f"Your prescription is {self.recipe.name}. {LINES[Stage.FAREWELL]}"
        return LINES.get(self.stage, "Keep still while the last response settles." if self.stage in REST_STAGES
                         else "Hold still while we record your baseline." if self.stage == Stage.CALIBRATE else "")

    def record(self):
        return {"stage": self.stage.value, "baseline": self.baseline, "gsr_span": self.span,
                "rounds": [asdict(result) for result in self.results],
                "recipe": asdict(self.recipe) if self.recipe else None,
                "delivery_complete": self.delivery_complete,
                "measurement": "Artistic signal mapping; not a measure of thoughts or desire."}
