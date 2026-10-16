LANGUAGE_ALIASES = {
    "en": "eng", "english": "eng",
    "de": "ger", "deu": "ger", "german": "ger", "deutsch": "ger",
    "fr": "fre", "fra": "fre", "french": "fre",
    "es": "spa", "spanish": "spa", "español": "spa",
    "it": "ita", "italian": "ita",
    "pt": "por", "portuguese": "por",
    "nl": "dut", "nld": "dut", "dutch": "dut",
    "pl": "pol", "polish": "pol",
    "sv": "swe", "swedish": "swe",
    "no": "nor", "nob": "nor", "norwegian": "nor",
    "da": "dan", "danish": "dan",
    "fi": "fin", "finnish": "fin",
    "ru": "rus", "russian": "rus",
    "uk": "ukr", "ukrainian": "ukr",
    "tr": "tur", "turkish": "tur",
    "ar": "ara", "arabic": "ara",
    "hi": "hin", "hindi": "hin",
    "ja": "jpn", "japanese": "jpn",
    "ko": "kor", "korean": "kor",
    "zh": "chi", "zho": "chi", "chinese": "chi",
    "cs": "cze", "ces": "cze", "czech": "cze",
    "hu": "hun", "hungarian": "hun",
    "el": "gre", "ell": "gre", "greek": "gre",
    "he": "heb", "hebrew": "heb",
    "th": "tha", "thai": "tha",
    "id": "ind", "indonesian": "ind",
    "vi": "vie", "vietnamese": "vie",
    "ro": "rum", "ron": "rum", "romanian": "rum",
    "ta": "tam", "tamil": "tam",
    "te": "tel", "telugu": "tel",
    "und": "",
}
ORIGINAL = "original"
FORCED_WORDS = ("forced", "signs", "songs")
SDH_WORDS = ("sdh", "cc", "hearing")


def canonical(lang):
    lang = (lang or "").strip().lower()
    return LANGUAGE_ALIASES.get(lang, lang)


def preferred(setting, original=""):
    langs = []
    for part in (setting or "").split(","):
        lang = canonical(part)
        if lang == ORIGINAL:
            lang = canonical(original)
        if lang and lang not in langs:
            langs.append(lang)
    return langs


def wants_original(setting):
    return ORIGINAL in [canonical(part) for part in (setting or "").split(",")]


def _title(track):
    return (track.get("title") or "").lower()


def _lang(track):
    lang = canonical(track.get("lang"))
    if lang:
        return lang
    title = _title(track)
    for word, code in LANGUAGE_ALIASES.items():
        if len(word) > 3 and word in title:
            return code
    return ""


def _is_forced(track):
    return bool(track.get("forced")) or any(w in _title(track) for w in FORCED_WORDS)


def choose_subtitle(tracks, sub_langs, mode, audio_lang):
    if mode == "off":
        return "no"
    subs = [t for t in tracks if t.get("type") == "sub"]
    if not subs or not sub_langs:
        return None
    matching = [t for t in subs if _lang(t) in sub_langs]
    audio_matches = canonical(audio_lang) in sub_langs if audio_lang else False
    if mode != "always" and audio_matches:
        forced = [t for t in matching if _is_forced(t)]
        return forced[0]["id"] if forced else "no"
    if not matching:
        return "no"

    def rank(track):
        return (
            sub_langs.index(_lang(track)),
            _is_forced(track),
            any(w in _title(track) for w in SDH_WORDS),
            not track.get("default"),
            track.get("external", False),
        )

    return sorted(matching, key=rank)[0]["id"]


def choose_audio(tracks, audio_langs):
    audio = [t for t in tracks if t.get("type") == "audio"]
    if not audio or not audio_langs:
        return None
    matching = [t for t in audio if _lang(t) in audio_langs]
    if not matching:
        return None
    matching.sort(key=lambda t: (audio_langs.index(_lang(t)), not t.get("default"), -(t.get("demux-channel-count") or 0)))
    return matching[0]["id"]
