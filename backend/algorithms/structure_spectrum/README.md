# Structure to Spectrum

Inference-only migration of the original RamanCloud molecular predictor.
`predictor.py` validates molecular inputs, generates SMILES conformers and runs
the three networks. `graph.py`, `net.py`, `modules/` and `spectra.py` retain the
original graph features, neural networks and spectral calculation.

## Models

Install `backend/requirements-structure.txt` with CPU PyTorch 2.5.1. Place these
private state dictionaries in the ignored `models/` directory:

- `2024_1_6_18_45_39.pth`: diagonal Hessian blocks
- `2024_1_6_18_44_49.pth`: off-diagonal Hessian blocks
- `2024_1_6_18_51_53.pth`: polarizability derivatives

Alternatively, set `RAMANCLOUD_STRUCTURE_MODEL_DIR` to the absolute path of a
private directory containing these three files. No weight files are packaged.
On minimal Debian/Ubuntu systems, install `libxrender1` for Open Babel's XYZ
format plugin; see `LOCAL_SETUP.md` for the complete setup.

Models load lazily on CPU. Coordinate derivatives require autograd during
inference; parameter gradients are disabled. One prediction runs at a time,
with at most 96 atoms including hydrogen.

## Output

The spectrum has 3,501 points over 500–4,000 cm⁻¹, normalized to its maximum.
The inherited settings are frequency scale 0.965, Lorentzian FWHM 12 cm⁻¹,
laser wavelength 532 nm and temperature 298 K. Uploaded XYZ coordinates are
preserved. SMILES conformers use deterministic ETKDG followed by MMFF.

The benzene sample is copied from the original site. The caffeine sample is
an RDKit/MMFF conformer generated from `Cn1c(=O)c2c(ncn2C)n(C)c1=O` with seed 42;
the original website listed caffeine but its XYZ file was missing.
