"""'No signal' is a claim about the code, not about our table.

When the Scheduler skips a module it records the reason, and a judge reads
that. If the reason says "no signal" while the truth is "our import table is
thirty entries long", the artefact is lying: a missing psycopg2 timeout, an
os.system injection and a yaml.load on untrusted input all get reported as
deliberately and correctly skipped.
"""

from pathlib import Path

import pytest

from augury.core.cartography import Cartographer, Signal


def write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import psycopg2", Signal.DATA),
        ("import pymysql", Signal.DATA),
        ("import MySQLdb", Signal.DATA),
        ("import pymongo", Signal.DATA),
        ("import motor", Signal.DATA),
        ("import boto3", Signal.NETWORK),
        ("from kafka import KafkaProducer", Signal.DISTRIBUTED),
        ("import aiokafka", Signal.DISTRIBUTED),
        ("import pika", Signal.DISTRIBUTED),
        ("import rq", Signal.DISTRIBUTED),
        ("import arq", Signal.DISTRIBUTED),
        ("import urllib.request", Signal.NETWORK),
        ("import http.client", Signal.NETWORK),
        ("import pickle", Signal.SECURITY),
        ("import yaml", Signal.SECURITY),
        ("import cryptography", Signal.SECURITY),
        ("import bcrypt", Signal.SECURITY),
        ("import passlib", Signal.SECURITY),
        ("import os", Signal.SECURITY),
    ],
)
def test_common_defect_carrying_imports_are_recognised(
    tmp_path: Path, source: str, expected: Signal
) -> None:
    """Every one of these produced an empty signal set, which meant the file
    was never read and the report called it 'no signal'."""
    write(tmp_path, "svc.py", source + "\n")

    assert expected in Cartographer(tmp_path).map().module("svc.py").signals


def test_a_django_model_reaches_the_data_specialist(tmp_path: Path) -> None:
    """A Django model file's entire risk surface is queries, transactions and
    N+1. It was routed to the network specialist and nowhere else."""
    from augury.core.layers import specialists_for

    write(tmp_path, "models.py", "from django.db import models\n")

    signals = Cartographer(tmp_path).map().module("models.py").signals
    names = {layer.name for layer in specialists_for(signals)}

    assert "data" in names


def test_a_module_with_no_imports_at_all_is_distinguished_from_an_unmatched_one(
    tmp_path: Path,
) -> None:
    """'Nothing here' and 'we did not recognise what is here' are different
    claims, and only one of them is about the code."""
    write(tmp_path, "constants.py", "TIMEOUT = 30\n")
    write(tmp_path, "exotic.py", "import some_library_we_have_never_heard_of\n")

    mapped = Cartographer(tmp_path).map()

    assert mapped.module("constants.py").signals == frozenset()
    assert mapped.module("exotic.py").unmatched_imports == frozenset(
        {"some_library_we_have_never_heard_of"}
    )
    assert mapped.module("constants.py").unmatched_imports == frozenset()
