import json
import os
import pytest
import time

from .. import utils

example_url = "http://www.example.com"


@pytest.fixture
def sample_dir(tmpdir):
    dir = tmpdir.mkdir("articles")
    for i in range(4):
        b = (i % 2 == 0)
        obj = {'title': 'a'+str(i),
               'has_reviews': b,
               'authors': ['abc xyz']}
        f = dir.join(str(i)+".json")
        f.write(json.dumps(obj))
        # with open(f"{tmpdir}/{i}.json", 'w+') as fp:
        # json.dump(obj, fp)
    return dir


def test_filter_articles(tmpdir, sample_dir):
    assert len(os.listdir(sample_dir)) == 4
    filtered_dir = os.path.join(tmpdir, 'filtered')
    os.mkdir(filtered_dir)
    utils.filter_articles(sample_dir, filtered_dir)
    assert len(os.listdir(filtered_dir)) == 2


def test_cook():
    soup = utils.cook(example_url)
    assert "Example Domain" in soup.get_text()

def test_cook_403():
    url = "https://en.wikipedia.org/wiki/HTTP_403"
    with pytest.raises(Exception, match = r"403.*[Ff]orbidden"):
        soup = utils.cook(url)
    pass

def test_cook_sleeps():
    startime = time.time()
    soup = utils.cook(example_url)
    assert time.time() - startime >= utils.MIN_TBR
