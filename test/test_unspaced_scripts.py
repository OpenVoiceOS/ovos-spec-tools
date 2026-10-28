"""OVOS-INTENT-2 §4.3 words in scripts that do not separate words with spaces.

Han, Hiragana, Katakana, Thai, Lao, Khmer and Myanmar count each character as
a word, so a keyword occurs inside an unspaced utterance, and a Latin keyword
occurs next to Han text with no space between them. Every other script keeps
the whole-word rule: ``art`` does not occur in ``start``.
"""
import pytest

from ovos_spec_tools import (required_keywords_reject, split_unspaced,
                             utterance_contains)


@pytest.mark.parametrize("utterance, keyword", [
    ("在WordNet中搜索同义词", "wordnet"),
    ("打开维基百科", "维基百科"),
    ("打开维基百科", "维基 百科"),
    ("ウィキペディアで東京を調べて", "ウィキペディア"),
    ("東京をウィキペディアで調べて", "ウィキペディア"),
    ("ค้นหาวิกิพีเดีย", "วิกิพีเดีย"),
])
def test_a_keyword_occurs_in_unspaced_text(utterance, keyword):
    assert utterance_contains(utterance, [keyword]) is True
    assert required_keywords_reject(utterance, [keyword]) is False


@pytest.mark.parametrize("utterance, keyword", [
    # a Latin word that runs on past the keyword is a different word
    ("在WordNetx中搜索", "wordnet"),
    ("打开百度", "维基百科"),
    ("start the timer", "art"),
    # Hangul separates words with spaces, so it keeps the whole-word rule
    ("위키백과에서 찾아줘", "위키"),
])
def test_a_keyword_does_not_occur(utterance, keyword):
    assert utterance_contains(utterance, [keyword]) is False
    assert required_keywords_reject(utterance, [keyword]) is True


def test_each_unspaced_character_is_a_word():
    assert split_unspaced("在WordNet中搜索") == "在 WordNet 中 搜 索"
    assert split_unspaced("打开 维基百科") == "打 开 维 基 百 科"


def test_text_without_an_unspaced_character_is_unchanged():
    assert split_unspaced("play  jazz") == "play  jazz"
    assert split_unspaced("위키백과에서 찾아줘") == "위키백과에서 찾아줘"
