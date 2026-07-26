"""Tests de la cache de extraccion por huella SHA-256.

Un LLM no es reproducible ni a temperatura 0. La cache hace que RE-IMPORTAR el
mismo documento de el mismo resultado y sin volver a llamar al modelo: la
segunda vez no se llama, se reutiliza la lectura guardada por su huella.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import IngestDocExtraction
from app.services.ingest import comprehension

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_ENGINE)
Base.metadata.create_all(bind=_ENGINE)
ORG = 446001

_DOC = {"filename": "BIA.xlsx", "sha256": "abc123def456", "format": "xlsx",
        "blocks": [{"type": "text", "ref": "p:1", "text": "contenido"}]}
_SMAP = {"doc_kind": "bia", "confidence": 0.9, "rationale": "x",
         "filename": "BIA.xlsx", "sha256": "abc123def456",
         "units": [{"target_entity": "bcm_scenario", "label": "e",
                    "decomposition_key": "k",
                    "rows": [{"fields": {"code": "ALT.01", "name": "Huelga",
                                         "family": "personnel"}}]}]}


@pytest.fixture()
def db():
    s = _Session()
    yield s
    s.query(IngestDocExtraction).filter_by(organization_id=ORG).delete(
        synchronize_session=False)
    s.commit()
    s.close()


def _fake_extract(*a, **k):
    """Simula la parte cara: la llamada al modelo + gap-fill."""
    return dict(_SMAP)


def test_la_primera_lectura_llama_al_modelo_y_la_segunda_no(db):
    calls = {"n": 0}

    def counting_extract(db_, org, document, smap, *a, **k):
        calls["n"] += 1
        return smap

    # Parcheamos las dos llamadas caras: la del mapa y el gap-fill. Dejamos la
    # cache real (es lo que probamos).
    with patch.object(comprehension, "_api_key_and_model",
                      return_value=("k", "m")), \
         patch.object(comprehension, "structured_message",
                      return_value=(dict(_SMAP), object())), \
         patch.object(comprehension, "_gap_fill", side_effect=counting_extract):

        # Primera lectura: llama al modelo y cachea
        out1 = comprehension.build_source_map(db, ORG, _DOC, use_cache=True)
        assert out1.get("from_cache") is not True
        assert db.query(IngestDocExtraction).filter_by(organization_id=ORG).count() == 1

        # Segunda lectura del MISMO documento: reutiliza, no llama al modelo
        out2 = comprehension.build_source_map(db, ORG, _DOC, use_cache=True)
        assert out2.get("from_cache") is True
        assert out2["units"] == out1["units"]


def test_use_cache_false_fuerza_lectura_fresca(db):
    db.add(IngestDocExtraction(organization_id=ORG, sha256="abc123def456",
                               prompt_version=comprehension.EXTRACTION_PROMPT_VERSION,
                               result=_SMAP))
    db.commit()
    with patch.object(comprehension, "_api_key_and_model", return_value=("k", "m")), \
         patch.object(comprehension, "structured_message",
                      return_value=(dict(_SMAP), object())), \
         patch.object(comprehension, "_gap_fill", side_effect=lambda *a, **k: dict(_SMAP)):
        out = comprehension.build_source_map(db, ORG, _DOC, use_cache=False)
    assert out.get("from_cache") is not True


def test_la_cache_no_cruza_organizaciones(db):
    db.add(IngestDocExtraction(organization_id=99999, sha256="abc123def456",
                               prompt_version=comprehension.EXTRACTION_PROMPT_VERSION,
                               result=_SMAP))
    db.commit()
    # Otra org con la misma huella no ve esa lectura
    assert comprehension._cache_get(db, ORG, "abc123def456") is None


def test_otra_version_de_prompt_invalida_la_cache(db):
    db.add(IngestDocExtraction(organization_id=ORG, sha256="abc123def456",
                               prompt_version="0", result=_SMAP))
    db.commit()
    # La version actual no encuentra la lectura guardada con version vieja
    assert comprehension._cache_get(db, ORG, "abc123def456") is None
