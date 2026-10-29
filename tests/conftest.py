from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.demo import sample_brief,sample_envelope,sample_alternatives,build_sample

@pytest.fixture
def concept():
    req=sample_brief();env=sample_envelope();planning=sample_alternatives(req,env)
    return req,env,planning

@pytest.fixture(scope='session')
def demo():
    return build_sample(include_reports=True)
