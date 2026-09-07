"""Extract person names from search result titles using NLP (spaCy NER).

Uses spaCy's Named Entity Recognition to identify PERSON entities in
search result titles, then ranks them by frequency. No hardcoded noise
word lists — the NLP model handles classification automatically.
"""

from collections import Counter
from typing import List

import spacy

# Lazy-load the spaCy model (loaded once, cached)
_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def extract_names_from_titles(titles: List[str], verified_titles: List[str] = None) -> List[str]:
    """Extract person names from search result titles.
    
    Names found in verified_titles get a massive priority boost.
    """
    if not titles and not verified_titles:
        return []

    nlp = _get_nlp()
    person_counts: Counter = Counter()
    
    if verified_titles is None:
        verified_titles = []
        
    all_titles_to_process = list(titles) + list(verified_titles)

    for title in all_titles_to_process:
        if not title or title == "Unknown":
            continue

        if title == title.lower():
            title = title.title()

        doc = nlp(title)
        
        # Boost factor: if it's in a verified title, it's highly likely to be the person
        boost = 100 if title in verified_titles else 1

        for ent in doc.ents:
            if ent.label_ == "PERSON":
                name = ent.text.strip()
                if len(name.split()) < 2:
                    continue
                name = " ".join(w.capitalize() for w in name.split())
                person_counts[name] += boost

    if not person_counts:
        return []

    # Sort by frequency (most common first), break ties alphabetically
    sorted_names = sorted(
        person_counts.keys(),
        key=lambda n: (-person_counts[n], n),
    )

    return sorted_names
