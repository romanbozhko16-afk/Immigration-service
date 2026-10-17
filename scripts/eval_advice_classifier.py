"""Measure the live model on the labeled phrases in evals/advice_phrases.json.

Costs money (one API call per phrase, about 40 calls). Needs ANTHROPIC_API_KEY in .env.
Run: uv run python scripts/eval_advice_classifier.py

Exit code 1 if any advice request is labeled "answer": that is the unsafe mistake. Labeling
a form question as an advice request is the safe direction and is only reported.
Prints labels only, never message text, so the output can be shared.
"""

import json
import sys
from collections import Counter

from uscis_assistant.config import get_settings
from uscis_assistant.forms.registry import REPO_ROOT
from uscis_assistant.interview.engine import load_active_bank
from uscis_assistant.llm.client import AnthropicLLM, LLMUnavailable
from uscis_assistant.llm.tasks import MessageKind, classify_message


def main() -> int:
    phrases = json.loads((REPO_ROOT / "evals/advice_phrases.json").read_text())
    questions = {q.id: q for q in load_active_bank().questions}
    llm = AnthropicLLM(get_settings())
    results: Counter[tuple[str, str]] = Counter()
    unsafe = 0
    for expected in ("advice_request", "form_question"):
        for index, phrase in enumerate(phrases[expected]):
            # A free-text question: the hardest context, where anything could be an answer.
            question = questions["status_current"]
            try:
                kind = classify_message(llm, question, phrase["text"], phrase["language"]).value
            except LLMUnavailable as exc:
                kind = f"unavailable ({exc})"
            results[(expected, kind)] += 1
            if expected == "advice_request" and kind == MessageKind.ANSWER:
                unsafe += 1
                print(f"UNSAFE: advice_request #{index} ({phrase['language']}) labeled answer")
    print(f"model: {get_settings().llm_model}, effort: {get_settings().llm_effort}")
    for (expected, kind), count in sorted(results.items()):
        print(f"{expected:15} -> {kind:20} {count}")
    return 1 if unsafe else 0


if __name__ == "__main__":
    sys.exit(main())
