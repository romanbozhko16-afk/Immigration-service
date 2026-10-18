"""BM25 keyword search over windows of consecutive sentences (no embeddings needed)."""

import math
import re
from collections import Counter

from uscis_assistant.reference.corpus import Corpus

STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how i if in is it its my of on or the this "
    "to was what when where which who why will with you your".split()
)
WINDOW, STEP = 3, 2  # sentences per window, and stride


def tokenize(text: str) -> list[str]:
    """Words, keeping hyphenated identifiers such as "i-94" or "a-number" as one term too."""
    tokens = []
    for word in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()):
        parts = word.split("-")
        if len(parts) > 1:
            tokens.append(word)
        tokens += [p for p in parts if p not in STOPWORDS and len(p) > 1]
    return tokens


class SearchIndex:
    def __init__(self, corpus: Corpus, k1: float = 1.5, b: float = 0.75):
        self.corpus = corpus
        sentences = corpus.sentences
        self.windows = [
            list(range(start, min(start + WINDOW, len(sentences))))
            for start in range(0, max(len(sentences) - WINDOW + 1, 1), STEP)
        ]
        self._docs = [
            Counter(tokenize(" ".join(sentences[i].text for i in window)))
            for window in self.windows
        ]
        self._lengths = [sum(doc.values()) for doc in self._docs]
        self._avg = sum(self._lengths) / max(len(self._lengths), 1)
        df = Counter(term for doc in self._docs for term in doc)
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self._k1, self._b = k1, b

    def search(self, query: str, limit: int = 4) -> list[tuple[float, list[int]]]:
        """Best windows as (score, sentence indexes); only windows sharing a query term."""
        terms = set(tokenize(query))
        scored = []
        for doc, length, window in zip(self._docs, self._lengths, self.windows, strict=True):
            score = 0.0
            for term in terms & doc.keys():
                tf = doc[term]
                norm = tf + self._k1 * (1 - self._b + self._b * length / self._avg)
                score += self._idf[term] * tf * (self._k1 + 1) / norm
            if score > 0:
                scored.append((score, window))
        scored.sort(key=lambda pair: -pair[0])
        return scored[:limit]
