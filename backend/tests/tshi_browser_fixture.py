"""Generate synthetic imaging fixtures, or verify the browser's MAT download."""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat


root = Path(__file__).resolve().parents[2] / 'logs'
if len(sys.argv) > 1 and sys.argv[1] == 'verify':
    result = loadmat(root / 'tshi-browser-result.mat')
    assert result['cube'].shape == (24, 20, 12)
    assert result['bm3d_center_image'].shape == (24, 20)
    assert np.isfinite(result['cube']).all()
    assert json.loads(result['history_json'][0])[0]['method'] == 'tshi'
    print('MAT_BROWSER_DOWNLOAD_OK')
else:
    root.mkdir(exist_ok=True)
    wave = np.linspace(400, 1800, 48)
    y, x = np.mgrid[:24, :20]
    spatial = 15 + 12 * np.exp(-((y - 10) ** 2 + (x - 8) ** 2) / 30) + x * .2
    cube = spatial[:, :, None] * (1 + np.exp(-((wave - 1100) / 100) ** 2))
    cube += np.random.default_rng(42).normal(0, .5, cube.shape)
    savemat(root / 'tshi-browser-input.mat', dict(cube=cube.reshape(-1, len(wave), order='F').T, x=wave.reshape(1, -1)))
    print(json.dumps(dict(height=24, width=20, center_wavenumber=float(wave[23]))))
