#!/usr/bin/env python3
"""Run the supplied private weights through the same inference code as the website."""
import argparse
import importlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed', action='store_true', help='Verify the installed Python package instead of this checkout')
    parser.add_argument('--structure', action='store_true', help='Also verify molecular prediction (three additional weights required)')
    parser.add_argument('--output', type=Path, help='Write the demo input and F2P/AirNet outputs as a text table')
    args = parser.parse_args()
    if not args.installed:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    package = 'ramancloud_backend' if args.installed else 'backend'
    try:
        import numpy as np
        root = Path(importlib.import_module(package).__file__).resolve().parent
        processing = importlib.import_module(package + '.algorithms.processing')
        f2p = importlib.import_module(package + '.algorithms.denoising.f2p.inference')
        airnet = importlib.import_module(package + '.algorithms.baseline_cor.airnet')
        sample = np.loadtxt(root / 'samples/tutorial_raman.txt')
        matrix = sample[:, 1].reshape(1, -1)
        results = {}
        outputs = []
        for name, module, run in [
            ('F2P', f2p, lambda: processing.denoise_batch(matrix, {}, 'f2p')),
            ('AirNet', airnet, lambda: processing.correct_baseline_batch(matrix, {}, 'airnet')[0]),
        ]:
            # Both loaders require an exact state-dictionary match; no keys are ignored.
            model, _ = module.load_model()
            output = run()
            if output.shape != matrix.shape or not np.isfinite(output).all():
                raise ValueError(f'{name}: invalid output shape or non-finite values')
            np.testing.assert_allclose(run(), output, rtol=1e-6, atol=1e-7)
            results[name] = {'model': type(model).__name__, 'state_entries': len(model.state_dict()),
                             'points': output.shape[1], 'strict_load': True, 'finite_and_repeatable': True}
            outputs.append(output[0])
        if args.structure:
            predictor = importlib.import_module(package + '.algorithms.structure_spectrum.predictor')
            molecule = predictor.from_xyz((predictor.ROOT / 'samples/benzene.xyz').read_text())
            prediction = predictor.predict(molecule)
            if len(prediction['intensity']) != 3501 or not np.isfinite(prediction['intensity']).all():
                raise ValueError('Structure prediction returned invalid intensities')
            results['structure'] = {'formula': prediction['molecule']['formula'], 'points': 3501,
                                    'models': len(predictor.load_models()), 'finite': True}
        if args.output:
            np.savetxt(args.output, np.column_stack([sample[:, 0], matrix[0], *outputs]),
                       header='wavenumber raw f2p airnet', fmt='%.12g')
        print(json.dumps(results, indent=2))
    except (ImportError, FileNotFoundError, ValueError, RuntimeError, AssertionError) as error:
        print(f'Verification failed: {error}\nSee LOCAL_SETUP.md for dependencies and private-weight paths.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
