"""Snapshot-bound configurable Hunspell and historical-name recognition.

A matching dictionary establishes only lexical recognition, not language,
correctness of OCR, or source fidelity. It never admits a custom lexicon entry.
"""
import ctypes
from ctypes.util import find_library
import hashlib
import os
from pathlib import Path
import re

from lexicon_store import canonical, valid_word

LANGUAGES = ("en_US", "de_DE", "fr_FR")  # Backward-compatible default
LOCALE_PATTERN = re.compile(r"^[a-z]{2,3}_[A-Z]{2}$")
DEFAULT_DICTIONARY_DIR = Path("/usr/share/hunspell")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class Spellcheck:
    """Load explicitly configured .aff/.dic pairs and optional sourced names.

    Each locale is mandatory, and every input is hashed for probe provenance.
    Historical names match only capitalized OCR tokens; they cannot silently
    suppress ordinary lowercase words. The human lexicon remains separate.
    """
    def __init__(self, dictionary_dir=DEFAULT_DICTIONARY_DIR, lexicon_words=None,
                 languages=LANGUAGES, historical_names=None):
        self.languages = tuple(languages)
        if (not self.languages or len(self.languages) != len(set(self.languages))
                or any(not isinstance(name, str) or
                       LOCALE_PATTERN.fullmatch(name) is None for name in self.languages)):
            raise ValueError("Dictionary locales must be unique identifiers like en_CA")
        root = Path(dictionary_dir)
        paths = {}
        for language in self.languages:
            aff = root / (language + ".aff")
            dic = root / (language + ".dic")
            if not aff.is_file() or not dic.is_file():
                raise RuntimeError(
                    f"Missing Hunspell {language} .aff/.dic in {root}; "
                    f"all configured dictionaries are required: {self.languages}")
            paths[language] = (aff, dic)

        libpath = find_library("hunspell-1.7")
        if not libpath:
            raise RuntimeError("The probe requires installed libhunspell-1.7")
        self.lib = ctypes.CDLL(libpath)
        self.lib.Hunspell_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.lib.Hunspell_create.restype = ctypes.c_void_p
        self.lib.Hunspell_spell.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lib.Hunspell_spell.restype = ctypes.c_int
        self.lib.Hunspell_destroy.argtypes = [ctypes.c_void_p]
        self.lib.Hunspell_destroy.restype = None
        self.lib.Hunspell_get_dic_encoding.argtypes = [ctypes.c_void_p]
        self.lib.Hunspell_get_dic_encoding.restype = ctypes.c_char_p
        self.handles = {}
        self.encodings = {}
        self.digests = {}
        self.lexicon_words = lexicon_words if lexicon_words is not None else set()
        self.historical_names = set()
        self.historical_names_sha256 = None
        if historical_names is not None:
            raw = Path(historical_names).read_bytes()
            if len(raw) > 10_000_000:
                raise ValueError("Historical name list too large")
            self.historical_names_sha256 = sha256(raw)
            for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
                name = line.strip()
                if not name or name.startswith("#"):
                    continue
                if (name != line or not valid_word(name) or not name[0].isupper()
                        or len(name) < 4):
                    raise ValueError(f"Invalid capitalized, single-token name on line {line_number}")
                key = canonical(name)
                if key in self.historical_names:
                    raise ValueError(f"Duplicate historical name on line {line_number}")
                self.historical_names.add(key)

        try:
            for language, (aff, dic) in paths.items():
                handle = self.lib.Hunspell_create(os.fsencode(aff), os.fsencode(dic))
                if not handle:
                    raise RuntimeError(f"Cannot initialize Hunspell {language}")
                self.handles[language] = handle
                encoding = self.lib.Hunspell_get_dic_encoding(handle)
                if not encoding:
                    raise RuntimeError(f"Hunspell {language} has no declared encoding")
                self.encodings[language] = encoding.decode("ascii")
                # Hash every dictionary pair by language in probe/sidecar provenance.
                self.digests[language] = {
                    "aff": sha256(aff.read_bytes()),
                    "dic": sha256(dic.read_bytes()),
                }
        except BaseException:
            self.close()
            raise

    def recognizes(self, word):
        if canonical(word) in self.lexicon_words:
            return True
        if (isinstance(word, str) and word and word[0].isupper()
                and canonical(word) in self.historical_names):
            return True
        for language in self.languages:
            try:
                encoded = word.encode(self.encodings[language])
            except (UnicodeEncodeError, LookupError):
                continue
            if self.lib.Hunspell_spell(self.handles[language], encoded):
                return True
        return False

    def close(self):
        for handle in self.handles.values():
            self.lib.Hunspell_destroy(handle)
        self.handles.clear()
