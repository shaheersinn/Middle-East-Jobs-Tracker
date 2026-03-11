"""
Department classifier.
Scores text against DEPARTMENTS taxonomy.
Phrase matches get a 2.5× boost over single keyword hits.
"""

import re
from classifier.taxonomy import DEPARTMENTS

PHRASE_BOOST = 2.5


class DepartmentClassifier:
    def __init__(self):
        self._depts = DEPARTMENTS

    def classify(self, text: str, top_n: int = 3) -> list[dict]:
        """
        Returns up to top_n depts sorted by descending score.
        Each entry: { department, score, matched_keywords }
        """
        t = text.lower()
        results = []

        for dept in self._depts:
            score = 0.0
            matched = []

            # Phrase pass (2.5× boost)
            for phrase in dept.get("phrases", []):
                if phrase.lower() in t:
                    score += PHRASE_BOOST
                    matched.append(phrase)

            # Keyword pass
            for kw in dept.get("keywords", []):
                pattern = r"\b" + re.escape(kw.lower()) + r"\b"
                if re.search(pattern, t):
                    score += 1.0
                    matched.append(kw)

            if score > 0:
                results.append({
                    "department":       dept["name"],
                    "score":            round(score, 2),
                    "matched_keywords": matched[:8],
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_n]

    def top_department(self, text: str) -> dict | None:
        hits = self.classify(text, top_n=1)
        return hits[0] if hits else None
