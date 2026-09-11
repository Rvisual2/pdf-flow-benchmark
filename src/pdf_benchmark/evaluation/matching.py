"""Historical FATA substring matching; presentation normalization is not implicit."""

from rapidfuzz import distance, fuzz


def find_best_match_and_normalized_distance(
    reference: str, markdown: str
) -> tuple[str | None, float | None]:
    if not reference or not markdown:
        return None, None
    alignment = fuzz.partial_ratio_alignment(reference, markdown)
    if alignment is None:
        return None, None
    best_match = markdown[alignment.dest_start : alignment.dest_end]
    edit_distance = distance.Levenshtein.distance(reference, best_match)
    maximum_length = max(len(reference), len(best_match))
    return best_match, edit_distance / maximum_length if maximum_length else 0.0
