import pytest

from .. import utils

def test_cook():
    soup = utils.cook("http://www.example.com")
    assert "Example Domain" in soup.get_text()