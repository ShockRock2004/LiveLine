import statistics
import time
from collections import deque
from dataclasses import asdict, dataclass, field

STAGES = ("endpoint_ms", "stt_ms", "llm_ms", "tts_ms", "total_ms")


def now_ms() -> float:
    return time.perf_counter() * 1000


@dataclass
class Turn:
    """One caller sentence and the reply. total_ms = caller stops talking -> first reply audio sent."""
    user_text: str = ""
    reply_text: str = ""
    endpoint_ms: float = 0
    stt_ms: float = 0
    llm_ms: float = 0
    tts_ms: float = 0
    total_ms: float = 0
    interrupted: bool = False


@dataclass
class Call:
    call_id: str
    provider: str
    started_at: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))
    turns: list[Turn] = field(default_factory=list)
    barge_in_ms: list[float] = field(default_factory=list)


class CallLog:
    def __init__(self):
        self.calls: deque[Call] = deque(maxlen=200)

    def start(self, call_id: str, provider: str) -> Call:
        self.calls.append(Call(call_id, provider))
        return self.calls[-1]

    def recent(self, limit: int = 20) -> list[dict]:
        return [asdict(c) for c in reversed(list(self.calls)[-limit:])]

    def summary(self) -> dict:
        turns = [t for c in self.calls for t in c.turns]
        result = {"calls": len(self.calls), "turns": len(turns)}
        for stage in STAGES:
            result[stage] = describe([getattr(t, stage) for t in turns])
        result["barge_in_ms"] = describe([ms for c in self.calls for ms in c.barge_in_ms])
        return result


def describe(values: list[float]) -> dict:
    if not values:
        return {"mean": 0, "p50": 0, "p95": 0}
    v = sorted(values)
    return {"mean": round(statistics.fmean(v)), "p50": round(statistics.median(v)),
            "p95": round(v[int(0.95 * (len(v) - 1))])}
