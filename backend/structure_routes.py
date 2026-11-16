"""Molecular prediction endpoints for the spectrum-structure workspace."""

import logging
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

if __package__:
    from .upload_archive import archive_uploads
else:
    from upload_archive import archive_uploads

router = APIRouter(prefix='/api/structure', tags=['spectrum-structure'])
logger = logging.getLogger(__name__)


@router.post('/conformer')
def prepare_conformer(
    source: Literal['smiles', 'drawing', 'xyz', 'demo'] = Form(...),
    smiles: str = Form('', max_length=4096),
    demo: Literal['benzene', 'caffeine'] = Form('benzene'),
    file: UploadFile | None = File(None),
):
    return structure_response(source, smiles, demo, file, preview=True)


@router.post('/predict')
def predict_structure(
    source: Literal['smiles', 'drawing', 'xyz', 'demo'] = Form(...),
    smiles: str = Form('', max_length=4096),
    demo: Literal['benzene', 'caffeine'] = Form('benzene'),
    file: UploadFile | None = File(None),
    share_data: bool = Form(True),
):
    return structure_response(source, smiles, demo, file, share_data=share_data)


def structure_response(source, smiles, demo, file, *, preview=False, share_data=False):
    try:
        if __package__:
            from .algorithms.structure_spectrum import predictor
        else:
            from algorithms.structure_spectrum import predictor
    except ImportError:
        logger.exception('Molecular prediction dependencies are unavailable')
        raise HTTPException(503, 'Molecular prediction is temporarily unavailable.') from None
    if not predictor.INFERENCE_LOCK.acquire(blocking=False):
        raise HTTPException(429, 'A molecular prediction is running. Please retry shortly.')
    started = time.monotonic()
    try:
        original = None
        filename = 'predicted_spectrum.txt'
        if source in ('smiles', 'drawing'):
            mol = predictor.from_smiles(smiles)
        elif source == 'demo':
            mol = predictor.from_xyz((predictor.ROOT / 'samples' / predictor.DEMO_FILES[demo]).read_text())
            filename = f'{demo}_predicted.txt'
        else:
            if file is None or not (file.filename or '').lower().endswith('.xyz'):
                raise HTTPException(400, 'Select an XYZ file.')
            original = file.file.read(256 * 1024 + 1)
            if len(original) > 256 * 1024:
                raise HTTPException(413, 'XYZ uploads are limited to 256 KiB.')
            try:
                mol = predictor.from_xyz(original.decode('utf-8-sig'))
            except UnicodeDecodeError:
                raise HTTPException(400, 'XYZ files must be UTF-8 text.') from None
            filename = Path(file.filename.replace('\\', '/')).stem + '_predicted.txt'
        result = {'molecule': predictor.describe_molecule(mol)} if preview else predictor.predict(mol)
        result['filename'] = filename
        result['elapsed_seconds'] = round(time.monotonic() - started, 2)
        if original is not None and not preview:
            result['data_sharing'] = archive_uploads([(file.filename, original)], source='v2',
                                                    module='structure_to_spectrum', share_data=share_data)
        return result
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except FileNotFoundError:
        raise HTTPException(503, 'Molecular prediction models are temporarily unavailable.') from None
    except HTTPException:
        raise
    except Exception:
        logger.exception('Molecular structure request failed')
        raise HTTPException(422, 'Could not process this structure. Check the molecule and its coordinates.') from None
    finally:
        predictor.INFERENCE_LOCK.release()
