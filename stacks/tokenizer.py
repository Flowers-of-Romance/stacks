"""日本語テキストの形態素解析。fugashi (MeCab) 優先、なければ簡易正規表現で処理。"""

import re

_tokenizer_backend = None  # "fugashi" | "regex"
_fugashi_tagger = None


def _init_fugashi():
    global _fugashi_tagger, _tokenizer_backend
    try:
        import fugashi
        _fugashi_tagger = fugashi.Tagger()
        _tokenizer_backend = "fugashi"
        return True
    except (ImportError, RuntimeError):
        return False


def _init():
    global _tokenizer_backend
    if _tokenizer_backend is not None:
        return
    if not _init_fugashi():
        _tokenizer_backend = "regex"


def tokenize(text):
    """テキストをスペース区切りのトークン列に変換する。"""
    _init()

    if _tokenizer_backend == "fugashi":
        words = _fugashi_tagger(text)
        tokens = [w.surface for w in words if w.surface.strip()]
        en_tokens = re.findall(r'[A-Za-z][A-Za-z0-9_\-]+', text)
        tokens.extend(t.lower() for t in en_tokens if len(t) > 1)
        return " ".join(tokens)

    # 簡易正規表現トークナイザ
    jp_tokens = re.findall(r'[\u4e00-\u9fff\u30a0-\u30ff]+', text)
    hira_tokens = re.findall(r'[\u3040-\u309f]{2,}', text)
    en_tokens = re.findall(r'[A-Za-z][A-Za-z0-9_\-]+', text)
    en_tokens = [t.lower() for t in en_tokens if len(t) > 1]
    return " ".join(jp_tokens + hira_tokens + en_tokens)


def get_backend():
    _init()
    return _tokenizer_backend
