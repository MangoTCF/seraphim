"""Hebrew letters, gematria and Seraphim phoneme rules.

Seraphim phonemes are whole Hebrew strings; only their gematria value is
phonemic. Values use Mispar Hechrachi with the final letters extended to
500-900 (the "slightly modified" table shown in Babelingua's video).
If a string's sum is not a phoneme, only its first (rightmost) letter counts.
"""

import itertools
import unicodedata

LETTER_VALUES = {
    "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9,
    "י": 10, "כ": 20, "ל": 30, "מ": 40, "נ": 50, "ס": 60, "ע": 70, "פ": 80,
    "צ": 90, "ק": 100, "ר": 200, "ש": 300, "ת": 400,
    "ך": 500, "ם": 600, "ן": 700, "ף": 800, "ץ": 900,
}

CONSONANT_VALUES = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 18, 20, 22, 24, 30, 40, 42, 50, 54,
    60, 70, 80, 90, 100, 200, 248, 300, 365, 374, 400, 500, 600, 613, 700,
    777, 800, 900,
)
VOWEL_VALUES = (1, 3, 15, 16, 26, 45, 86, 314)
# 1 and 3 are both; a brightness mark is what makes them vowels.
AMBIGUOUS_VALUES = set(CONSONANT_VALUES) & set(VOWEL_VALUES)

# Names of God may not be used as phonemes. Substitutes such as אלוקים or
# הויה are fine (Babelingua's own demo leans on them heavily).
DIVINE_NAMES = {
    "יהוה", "יה", "יהו", "אל", "אלה", "אלוה", "אלהים", "אלוהים", "שדי",
    "אדני", "אדוני", "צבאות", "אהיה", "אלהי", "אלוהי", "אלי", "אלהינו",
    "אלוהינו", "יי",
}

DAGESH = "ּ"
SHIN_DOT = "ׁ"
SIN_DOT = "ׂ"
NIQQUD_VOWELS = {
    "ְ": "ə",   # sheva
    "ֱ": "ɛ",   # hataf segol
    "ֲ": "a",   # hataf patah
    "ֳ": "ɔ",   # hataf qamats
    "ִ": "i",   # hiriq
    "ֵ": "e",   # tsere
    "ֶ": "ɛ",   # segol
    "ַ": "a",   # patah
    "ָ": "ɔ",   # qamats (Tiberian)
    "ֹ": "o",   # holam
    "ֺ": "o",   # holam haser for vav
    "ֻ": "u",   # qubuts
    "ׇ": "ɔ",   # qamats qatan
}

# Tiberian-ish values; the demo's [fəðəv], [θəzən], [xəv] show soft begadkefat.
SOFT = {"ב": "v", "ג": "ɣ", "ד": "ð", "כ": "x", "ך": "x", "פ": "f", "ף": "f", "ת": "θ"}
HARD = {"ב": "b", "ג": "g", "ד": "d", "כ": "k", "ך": "k", "פ": "p", "ף": "p", "ת": "t"}
PLAIN = {
    "א": "ʔ", "ה": "h", "ו": "w", "ז": "z", "ח": "ħ", "ט": "tˤ", "י": "j",
    "ל": "l", "מ": "m", "ם": "m", "נ": "n", "ן": "n", "ס": "s", "ע": "ʕ",
    "צ": "sˤ", "ץ": "sˤ", "ק": "q", "ר": "r", "ש": "ʃ",
}

FINAL_OF = {"כ": "ך", "מ": "ם", "נ": "ן", "פ": "ף", "צ": "ץ"}


def letters(s):
    """Base letters only, niqqud and marks stripped."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if c in LETTER_VALUES)


def gematria(s):
    return sum(LETTER_VALUES[c] for c in letters(s))


def phoneme_value(s):
    """The Seraphim phoneme a string spells, or None if it spells nothing."""
    ls = letters(s)
    if not ls:
        return None
    total = gematria(ls)
    if total in CONSONANT_VALUES or total in VOWEL_VALUES:
        return total
    first = LETTER_VALUES[ls[0]]
    return first


def is_divine_name(s):
    return letters(s) in DIVINE_NAMES


def classify(value, marked):
    """'V', 'C' or None for a phoneme value; marked = has a brightness mark."""
    if value is None:
        return None
    if value in AMBIGUOUS_VALUES:
        return "V" if marked else "C"
    if value in VOWEL_VALUES:
        return "V"
    if value in CONSONANT_VALUES:
        return "C"
    return None


def clusters(s):
    """Split a string into (letter, marks) clusters."""
    out = []
    for c in unicodedata.normalize("NFD", s):
        if c in LETTER_VALUES:
            out.append([c, ""])
        elif out and unicodedata.category(c) == "Mn":
            out[-1][1] += c
    return out


VOWEL_PHONES = set("aeiouɛɔəy")
GUTTURALS = {"ʔ", "h", "ħ", "ʕ", "r"}


def _consonant(ch, marks, begadkefat):
    if ch in SOFT:
        return HARD[ch] if DAGESH in marks or begadkefat == "hard" else SOFT[ch]
    if ch == "ש":
        return "s" if SIN_DOT in marks else "ʃ"
    return PLAIN[ch]


def _matres(cl, begadkefat):
    """Unpointed Hebrew read with vowel letters, the way people read it:
    ו and י after a consonant are the vowels u/o and i, final א/ה is a, and
    the vowel slipped between two consonants is a next to a guttural, e in
    the first slot of the string (segolate-style) and ə after that.
    אלוקים -> ʔaluqim, הבא -> hava, וו -> wu."""
    phones = []
    for i, (ch, marks) in enumerate(cl):
        last = i == len(cl) - 1
        after_consonant = bool(phones) and phones[-1] not in VOWEL_PHONES
        if last and ch == "ה" and phones and not after_consonant:
            continue                    # final ה after a vowel is silent
        if after_consonant and DAGESH not in marks:
            if ch == "ו":
                phones.append("o" if last else "u")
                continue
            if ch == "י":
                phones.append("i")
                continue
            if ch == "א" or (ch == "ה" and last):
                phones.append("a")
                continue
        c = _consonant(ch, marks, begadkefat)
        if after_consonant:
            if phones[-1] in GUTTURALS or c in GUTTURALS:
                phones.append("a")
            elif not any(p in VOWEL_PHONES for p in phones):
                phones.append("e")
            else:
                phones.append("ə")
        phones.append(c)
    if len(phones) == 1:
        phones.append("a" if phones[0] in GUTTURALS else "e")
    return phones


def to_ipa(s, begadkefat="soft", reading="matres"):
    """Pronounce a Hebrew string.

    reading='matres' (default) reads vowel letters as vowels (see _matres).
    reading='demo' does exactly what Babelingua's demo does: consonants joined
    by schwa, nothing after the last one, a lone letter gets a trailing schwa.
    A string with niqqud is always read as pointed Hebrew: bare letters are
    plain consonants, and final unpointed א/ה and mater י are silent."""
    cl = clusters(s)
    pointed = any(m in NIQQUD_VOWELS or m == "\u05b9" for _, ms in cl for m in ms) or any(
        ch == "ו" and DAGESH in ms for ch, ms in cl[1:])
    if not pointed and reading == "matres":
        return _matres(cl, begadkefat)
    phones = []
    for i, (ch, marks) in enumerate(cl):
        vowel = next((NIQQUD_VOWELS[m] for m in marks if m in NIQQUD_VOWELS), None)
        dagesh = DAGESH in marks
        last = i == len(cl) - 1
        if ch == "ו" and dagesh and vowel is None and i > 0:
            phones.append("u")          # shuruk
            continue
        if ch == "ו" and "\u05b9" in marks and i > 0:
            phones.append("o")          # holam male
            continue
        if pointed and vowel is None and not dagesh:
            prev_vowel = phones and phones[-1] in "aeiouɛɔə"
            if last and ch in "אה" and prev_vowel:
                continue                # silent final mater
            if ch == "י" and phones and phones[-1] in "ie" and not last:
                continue                # hiriq/tsere male
        if ch in SOFT:
            hard = dagesh or begadkefat == "hard"
            c = HARD[ch] if hard else SOFT[ch]
        elif ch == "ש":
            c = "s" if SIN_DOT in marks else "ʃ"
        else:
            c = PLAIN[ch]
        if "\u05b9" in marks and ch != "ו":
            vowel = "o"                 # holam on a consonant
        phones.append(c)
        if vowel is not None:
            phones.append(vowel)
        elif not pointed and (not last or len(cl) == 1):
            phones.append("ə")
    return phones


def spell(value, limit=8, max_len=4):
    """Hebrew strings whose gematria is exactly `value`, shortest and most
    pronounceable first, never a divine name. Final forms only at the end."""
    medial = [c for c in LETTER_VALUES if c not in FINAL_OF.values()]
    finals_ok = set(FINAL_OF.values())
    found = []
    for n in range(1, max_len + 1):
        for combo in itertools.combinations_with_replacement(sorted(medial, key=LETTER_VALUES.get, reverse=True), n):
            if sum(LETTER_VALUES[c] for c in combo) != value:
                continue
            for perm in set(itertools.permutations(combo)):
                w = list(perm)
                if w[-1] in FINAL_OF:
                    w[-1] = FINAL_OF[w[-1]]
                    if sum(LETTER_VALUES[c] for c in w) != value:
                        continue
                w = "".join(w)
                if not is_divine_name(w) and phoneme_value(w) == value:
                    found.append(w)
        # Final letters (500-900) can also be reached directly at the end.
        for f in finals_ok:
            rest = value - LETTER_VALUES[f]
            if rest < 0 or (rest == 0 and n != 1):
                continue
            for w in spell_exact_medial(rest, n - 1, medial):
                cand = w + f
                if not is_divine_name(cand) and phoneme_value(cand) == value:
                    found.append(cand)
        if len(found) >= limit * 4:
            break
    found = sorted(set(found), key=lambda w: (len(w), -pronounceability(w), w))
    return found[:limit]


def spell_exact_medial(value, n, medial):
    if n == 0:
        return [""] if value == 0 else []
    out = []
    for combo in itertools.combinations_with_replacement(medial, n):
        if sum(LETTER_VALUES[c] for c in combo) == value:
            out.extend("".join(p) for p in set(itertools.permutations(combo)))
    return out


def pronounceability(w):
    # Favour sonorants and alternation of letter classes; purely cosmetic.
    sonorant = set("למנןםרוי")
    score = sum(c in sonorant for c in w)
    score -= sum(1 for a, b in zip(w, w[1:]) if a == b)
    return score
