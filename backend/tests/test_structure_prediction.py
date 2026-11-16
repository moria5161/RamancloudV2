"""Focused checks for molecular input, inference, and the prediction endpoint."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

pytest.importorskip('rdkit')
pytest.importorskip('torch_geometric')
pytest.importorskip('openbabel')

from backend.app import app
from backend.algorithms.structure_spectrum import predictor


def test_xyz_preserves_coordinates_and_rejects_invalid_input():
    text = (predictor.ROOT / 'samples/benzene.xyz').read_text()
    mol = predictor.from_xyz(text)
    expected = np.array([[float(v) for v in line.split()[1:]] for line in text.splitlines()[2:2 + mol.GetNumAtoms()]])
    np.testing.assert_allclose(mol.GetConformer().GetPositions(), expected)
    for invalid in ['97\n\n', text.replace('C', 'Unknown', 1), text.replace(text.splitlines()[2], 'C nan 0 0')]:
        with pytest.raises(ValueError):
            predictor.from_xyz(invalid)
    with pytest.raises(ValueError):
        predictor.from_smiles('CC.CC')
    with pytest.raises(ValueError):
        predictor.from_smiles('not smiles')


def test_smiles_conformer_is_reproducible():
    first = predictor.from_smiles('CCCO')
    second = predictor.from_smiles('CCCO')
    np.testing.assert_allclose(first.GetConformer().GetPositions(), second.GetConformer().GetPositions())


def test_prediction_endpoint_and_original_upload_opt_out(monkeypatch):
    if not (predictor.ROOT / 'models/2024_1_6_18_45_39.pth').exists():
        pytest.skip('Private model weights are not installed')
    from backend import structure_routes
    archived = []
    monkeypatch.setattr(structure_routes, 'archive_uploads', lambda uploads, **kw: archived.append((uploads, kw)) or {'status': 'disabled'})
    text = (predictor.ROOT / 'samples/benzene.xyz').read_bytes()
    with TestClient(app) as client:
        response = client.post('/api/structure/predict', data={'source': 'xyz', 'share_data': 'false'}, files={'file': ('benzene.xyz', text, 'text/plain')})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['wavenumber'] == list(range(500, 4001))
    assert len(result['intensity']) == 3501
    assert np.isfinite(result['intensity']).all()
    assert max(result['intensity']) == 1
    assert result['molecule']['formula'] == 'C6H6'
    assert len(result['molecule']['atoms']) == 12
    assert archived[0][0] == [('benzene.xyz', text)]
    assert archived[0][1]['share_data'] is False


def test_prediction_rejects_missing_input_and_concurrent_work():
    with TestClient(app) as client:
        assert client.post('/api/structure/predict', data={'source': 'xyz'}).status_code == 400
        assert client.post('/api/structure/predict', data={'source': 'smiles', 'smiles': 'x' * 4097}).status_code == 422
        with predictor.INFERENCE_LOCK:
            response = client.post('/api/structure/predict', data={'source': 'demo'})
            assert response.status_code == 429


@pytest.mark.parametrize('source', ['demo', 'smiles', 'drawing', 'xyz'])
def test_conformer_preview_without_prediction_or_archiving(monkeypatch, source):
    from backend import structure_routes

    def unexpected(*args, **kwargs):
        pytest.fail('Preview must not run spectral inference or archive uploads')

    monkeypatch.setattr(predictor, 'predict', unexpected)
    monkeypatch.setattr(predictor, 'load_models', unexpected)
    monkeypatch.setattr(structure_routes, 'archive_uploads', unexpected)
    text = (predictor.ROOT / 'samples/benzene.xyz').read_bytes()
    files = {'file': ('benzene.xyz', text, 'text/plain')} if source == 'xyz' else None
    with TestClient(app) as client:
        response = client.post('/api/structure/conformer', data={'source': source, 'smiles': 'CCCO'}, files=files)
    assert response.status_code == 200, response.text
    result = response.json()
    assert 'intensity' not in result
    assert 'wavenumber' not in result
    assert 'data_sharing' not in result
    assert result['molecule']['formula'] == ('C6H6' if source in ('demo', 'xyz') else 'C3H8O')
    positions = [atom['position'] for atom in result['molecule']['atoms']]
    assert np.isfinite(positions).all()
    if source == 'xyz':
        expected = [[float(value) for value in line.split()[1:]] for line in text.decode().splitlines()[2:14]]
        np.testing.assert_allclose(positions, expected)


def test_conformer_rejects_invalid_input():
    with TestClient(app) as client:
        assert client.post('/api/structure/conformer', data={'source': 'xyz'}).status_code == 400
        assert client.post('/api/structure/conformer', data={'source': 'smiles', 'smiles': 'not smiles'}).status_code == 400
        assert client.post('/api/structure/conformer', data={'source': 'drawing', 'smiles': ''}).status_code == 400
