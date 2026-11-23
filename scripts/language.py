"""Detect the natural language of a SKILL.md file.

Two stages, because langdetect alone is unreliable on short CJK text:
  1. Script check: if >30% of letters are outside Latin, classify by script
     (zh / ja / ko / ru-cyrillic / other).
  2. Otherwise run langdetect on the prose only (front matter, code blocks,
     inline code and URLs removed). English requires p(en) >= EN_MIN_PROB.

Returns (language_code, confidence). Deterministic: langdetect is seeded.
"""
import re

from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0

EN_MIN_PROB = 0.90
NONLATIN_THRESHOLD = 0.30
MAX_PROSE_CHARS = 5000

_FRONTMATTER = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.S)
_FENCED = re.compile(r"```.*?```|~~~.*?~~~", re.S)
_INLINE = re.compile(r"`[^`\n]*`")
_URL = re.compile(r"https?://\S+")
_HTML = re.compile(r"<[^>]+>")


def prose(text: str) -> str:
    t = _FRONTMATTER.sub("", text or "")
    for pat in (_FENCED, _INLINE, _URL, _HTML):
        t = pat.sub(" ", t)
    return t[:MAX_PROSE_CHARS]


def _script_language(letters):
    joined = "".join(letters)
    if re.search(r"[぀-ヿ]", joined):
        return "ja"
    if re.search(r"[가-힯]", joined):
        return "ko"
    if re.search(r"[一-鿿]", joined):
        return "zh"
    if re.search(r"[Ѐ-ӿ]", joined):
        return "cyrillic"
    return "other-nonlatin"


def detect(text: str):
    body = prose(text)
    letters = [ch for ch in body if ch.isalpha()]
    if len(letters) < 40:
        return "unknown", 0.0
    nonlatin = sum(1 for ch in letters if ord(ch) > 0x24F) / len(letters)
    if nonlatin > NONLATIN_THRESHOLD:
        return _script_language(letters), round(nonlatin, 3)
    try:
        langs = detect_langs(body)
    except LangDetectException:
        return "unknown", 0.0
    top = langs[0]
    if top.lang == "en" and top.prob < EN_MIN_PROB:
        return "mixed", round(top.prob, 3)
    return top.lang, round(top.prob, 3)


def is_english(text: str) -> bool:
    return detect(text)[0] == "en"
