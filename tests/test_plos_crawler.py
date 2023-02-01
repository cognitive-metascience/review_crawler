import os
import pytest

from .. import plos_crawler

dumpdir = os.path.join(os.path.dirname(__file__), 'dumps')

# TODO: logs are currently saved to the base folder (/review_crawler/logs),
#        could be saved instead to /review_crawler/tests/logs

