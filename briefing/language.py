"""Offline output-language check. Source text and evidence never pass through it."""
from __future__ import annotations

import re
from functools import lru_cache

from langdetect import DetectorFactory, LangDetectException
from langdetect.detector_factory import PROFILES_DIRECTORY


@lru_cache(maxsize=1)
def factory() -> DetectorFactory:
    result = DetectorFactory()
    result.load_profile(PROFILES_DIRECTORY)
    result.set_seed(0)
    return result


def non_english_language(text: str) -> str:
    """Return only a confidently detected non-English language.

    Short brand names and ambiguous fragments are not reliable language samples.
    The prompt remains responsible for English in those cases. No translation,
    paid repair request or source-text normalisation takes place here.
    """
    # Markup is escaped by the renderer; tag names are not natural language.
    text = re.sub(r"<[^>]*>", " ", text)
    if len(re.findall(r"[^\W\d_]+", text, re.UNICODE)) < 4:
        return ""
    detector = factory().create()
    detector.append(text)
    try:
        languages = detector.get_probabilities()
    except LangDetectException:
        return ""
    if languages and languages[0].lang != "en" and languages[0].prob >= 0.90:
        return languages[0].lang
    return ""
