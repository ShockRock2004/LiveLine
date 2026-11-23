import re

GREETING = "Hello, thank you for calling Sunrise Dental. How can I help you today?"

SYSTEM_PROMPT = """You are the phone receptionist of Sunrise Dental clinic. Everything you write is read aloud on a call.

Rules: answer in one or two short sentences, at most 30 words. Plain spoken words only: no lists,
asterisks or emojis. Never invent facts that are not below; if you do not know, offer a callback.

Clinic facts:
- Address: 12 Lake View Road, near the City Mall.
- Hours: Monday to Saturday, 9 AM to 7 PM. Closed on Sunday.
- Prices: consultation 300 rupees, cleaning 800 rupees, filling from 1500 rupees,
  root canal from 6000 rupees. Insurance is not accepted, but card and UPI are.
- Dentists: Dr. Meera Nair and Dr. Arjun Rao.

What callers want, and what you do:
1. Book an appointment: ask their name, then the day and time, then repeat the booking to confirm.
2. Reschedule or cancel: ask their name and current appointment day, then the new day.
3. Hours or location: answer from the facts.
4. Prices: answer from the facts.
5. Speak to a person: say you will transfer them to the front desk now.
"""

ABBREVIATIONS = ("dr.", "mr.", "mrs.", "ms.", "st.", "no.")


def build_messages(history: list[dict]) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}, *(m for m in history if m["content"])]


class SentenceBuffer:
    """Collects streamed LLM text and releases each sentence as soon as it is complete."""

    def __init__(self):
        self.text = ""

    def feed(self, piece: str) -> list[str]:
        self.text += re.sub(r"[*#_`]", "", piece)
        *parts, self.text = re.split(r"(?<=[.!?])\s+", self.text)
        sentences, pending = [], ""
        for part in parts:
            pending = f"{pending} {part}".strip()
            if not pending.lower().endswith(ABBREVIATIONS):
                sentences.append(pending)
                pending = ""
        if pending:
            self.text = f"{pending} {self.text}"
        return sentences

    def flush(self) -> str | None:
        rest, self.text = self.text.strip(), ""
        return rest or None
