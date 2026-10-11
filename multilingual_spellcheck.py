"""Snapshot-bound English, German and French Hunspell recognition.

A matching dictionary establishes only lexical recognition, not language,
correctness of OCR, or source fidelity. It never admits a custom lexicon entry.
"""
import ctypes
from ctypes.util import find_library
import hashlib
import os
from pathlib import Path

from lexicon_store import canonical

LANGUAGES = ("en_US", "de_DE", "fr_FR")
DEFAULT_DICTIONARY_DIR = Path("/usr/share/hunspell")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class Spellcheck:
    """Require all 3 named aff/dic pairs; fail closed when any is unavailable.

    Keep Hunspell's per-dictionary affix rules and character encodings.
    Membership in the separately human-approved lexicon is checked first.
    """
    def __init__(self, dictionary_dir=DEFAULT_DICTIONARY_DIR, lexicon_words=None):
        root = Path(dictionary_dir)
        paths = {}
        for language in LANGUAGES:
            aff = root / (language + ".aff")
            dic = root / (language + ".dic")
            if not aff.is_file() or not dic.is_file():
                raise RuntimeError(
                    f"Missing Hunspell {language} .aff/.dic in {root}; "
                    "all en_US, de_DE and fr_FR dictionaries are required")
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
        for language in LANGUAGES:
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
