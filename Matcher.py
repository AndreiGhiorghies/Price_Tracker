import re
import unicodedata
import math

def strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def normalize(s: str) -> str:
    s = strip_accents(s).lower()
    s = re.sub(r"[/_+,;:~]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def tokenize_keep_quotes(q: str):
    phrases = re.findall(r'"([^"]+)"', q)
    q_wo = re.sub(r'"[^"]+"', " ", q)
    tokens = re.findall(r"[a-z0-9\-]+", normalize(q_wo))
    return [normalize(p) for p in phrases], tokens

def split_letters_digits(tok: str):
    m = re.fullmatch(r"([a-z]+)-?([0-9][a-z0-9]*)", tok)
    if not m: return None
    return m.group(1), m.group(2)

def build_token_pattern(tok: str) -> str:
    if split := split_letters_digits(tok):
        letters, digits = split
        return rf"\b{re.escape(letters)}\s*-?\s*{re.escape(digits)}\b"
    if re.fullmatch(r"[a-z]{2,}[0-9][a-z0-9]*", tok):
        return rf"\b{re.escape(tok)}\b"
    return rf"\b{re.escape(tok)}\b"

def build_generic_matcher(query: str):
    must_phrases, tokens = tokenize_keep_quotes(query)
    pos_patterns = [build_token_pattern(t) for t in tokens]
    pos_res = [re.compile(p, re.IGNORECASE) for p in pos_patterns]
    phrase_res = [re.compile(re.escape(normalize(p)), re.IGNORECASE) for p in must_phrases]

    n = len(pos_res)
    if n <= 3:
        need = n
    elif n <= 6:
        need = n - 1
    else:
        need = math.ceil(0.7 * n)

    def matcher(title: str) -> bool:
        t = normalize(title)
        for pr in phrase_res:
            if not pr.search(t):
                return False
        hits = sum(1 for r in pos_res if r.search(t))
        return hits >= need

    return matcher
