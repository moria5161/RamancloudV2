"""Bounded, CPU-only inference using the original RamanCloud model weights."""

from functools import lru_cache
import os
from pathlib import Path
from threading import Lock

import numpy as np
import torch
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolDescriptors
from openbabel import openbabel as ob
from torch_geometric.nn import radius_graph

from .constant import atom_masses
from .graph import rdmol2pt
from .net import Net
from .spectra import hessfreq, chain_rule_raman, get_raman_act, freqaraman2spec

ROOT = Path(__file__).resolve().parent
MAX_ATOMS = 96
INFERENCE_LOCK = Lock()
DEMO_FILES = {'benzene': 'benzene.xyz', 'caffeine': 'caffeine.xyz'}


def validate_molecule(mol):
    if mol is None or not 4 <= mol.GetNumAtoms() <= MAX_ATOMS:
        raise ValueError(f'The predictor requires 4 to {MAX_ATOMS} atoms, including hydrogens.')
    if any(not 1 <= atom.GetAtomicNum() <= 35 for atom in mol.GetAtoms()):
        raise ValueError('This model supports atomic numbers 1 to 35 only.')
    if len(Chem.GetMolFrags(mol)) != 1 or not mol.GetNumBonds():
        raise ValueError('Provide one connected molecule, with all hydrogens included in XYZ files.')


def from_smiles(text):
    if not text.strip() or len(text) > 4096:
        raise ValueError('Provide a SMILES string of at most 4096 characters.')
    mol = Chem.MolFromSmiles(text.strip())
    if mol is None:
        raise ValueError('Invalid SMILES. Check the molecular structure.')
    mol = Chem.AddHs(mol)
    validate_molecule(mol)
    if not AllChem.MMFFHasAllMoleculeParams(mol):
        raise ValueError('MMFF cannot optimize this molecule. Upload a valid XYZ conformer instead.')
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    params.maxIterations = 200
    if AllChem.EmbedMolecule(mol, params) != 0:
        raise ValueError('Could not generate a 3D conformer. Try uploading an XYZ file.')
    status = AllChem.MMFFOptimizeMolecule(mol, maxIters=1000)
    if status != 0:
        raise ValueError('Conformer optimization did not converge. Upload an optimized XYZ file.')
    return mol


def from_xyz(text):
    lines = text.splitlines()
    try:
        count = int(lines[0])
        if not 4 <= count <= MAX_ATOMS or len(lines) < count + 2 or any(line.strip() for line in lines[count + 2:]):
            raise ValueError()
        for line in lines[2:count + 2]:
            fields = line.split()
            if len(fields) != 4 or not np.isfinite([float(v) for v in fields[1:]]).all():
                raise ValueError()
    except (ValueError, IndexError):
        raise ValueError(f'Invalid XYZ: expected one molecule with 4 to {MAX_ATOMS} atoms and finite x, y, z coordinates.') from None
    mol = Chem.MolFromXYZBlock(text)
    if mol is None:
        raise ValueError('Could not parse the XYZ molecule.')
    conversion = ob.OBConversion()
    conversion.SetInFormat('xyz')
    obmol = ob.OBMol()
    if not conversion.ReadString(obmol, text):
        raise ValueError('Could not determine bonds from the XYZ coordinates.')
    editable = Chem.RWMol(mol)
    bond_types = [Chem.BondType.SINGLE, Chem.BondType.DOUBLE, Chem.BondType.TRIPLE]
    for bond in ob.OBMolBondIter(obmol):
        order = bond.GetBondOrder()
        if not bond.IsAromatic() and order not in (1, 2, 3):
            raise ValueError('Unsupported bond type in the XYZ structure.')
        editable.AddBond(bond.GetBeginAtomIdx() - 1, bond.GetEndAtomIdx() - 1,
                         Chem.BondType.AROMATIC if bond.IsAromatic() else bond_types[order - 1])
    mol = editable.GetMol()
    mol.UpdatePropertyCache(strict=False)
    validate_molecule(mol)
    return mol


@lru_cache(maxsize=1)
def load_models():
    model_dir = Path(os.environ.get('RAMANCLOUD_STRUCTURE_MODEL_DIR', ROOT / 'models'))
    definitions = [
        ('2024_1_6_18_45_39.pth', dict(scalar_outsize=1, irreps_out=None, summation=False, out_type='scalar', grad_type='Hi')),
        ('2024_1_6_18_44_49.pth', dict(scalar_outsize=1, irreps_out=None, summation=False, out_type='scalar', grad_type='Hij')),
        ('2024_1_6_18_51_53.pth', dict(scalar_outsize=2, irreps_out='2e', summation=True, out_type='2_tensor', grad_type='polar')),
    ]
    models = []
    for filename, options in definitions:
        path = model_dir / filename
        if not path.is_file():
            raise FileNotFoundError('Structure-to-spectrum model weights are unavailable.')
        model = Net(num_features=128, act='swish', maxl=3, num_block=3, num_radial=32,
                    attention_head=8, rc=5.0, max_atomic_number=35, device='cpu', **options)
        model.load_state_dict(torch.load(path, map_location='cpu', weights_only=True))
        model.eval()
        model.requires_grad_(False)
        models.append(model)
    return models


def validated_positions(mol):
    positions = np.asarray(mol.GetConformer().GetPositions())
    if not np.isfinite(positions).all() or np.max(np.abs(positions)) > 10000:
        raise ValueError('Molecular coordinates must be finite and expressed in angstroms.')
    distances = np.linalg.norm(positions[:, None] - positions[None, :], axis=-1)
    np.fill_diagonal(distances, np.inf)
    if distances.min() < 0.1:
        raise ValueError('Some atoms overlap. Check the XYZ coordinates.')
    return positions


def describe_molecule(mol):
    positions = validated_positions(mol)
    return {
        'atoms': [{'element': atom.GetSymbol(), 'position': positions[i].tolist()} for i, atom in enumerate(mol.GetAtoms())],
        'bonds': [[bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(), float(bond.GetBondTypeAsDouble())] for bond in mol.GetBonds()],
        'formula': rdMolDescriptors.CalcMolFormula(mol),
        'xyz': Chem.MolToXYZBlock(mol),
    }


def predict(mol):
    positions = validated_positions(mol)
    data = rdmol2pt(mol, 'molecule')
    edges = radius_graph(data.atoms_pos, r=5.0)
    arguments = dict(atoms_x=data.atoms_x, atoms_edge_index=edges,
                     atoms_batch=torch.zeros(len(data.atoms_x), dtype=torch.long),
                     bonds_x=data.x, bonds_edge_index=data.edge_index, bonds_edge_attr=data.edge_attr,
                     bonds_batch=torch.zeros(len(data.x), dtype=torch.long))
    # Coordinate derivatives are required by these models even in evaluation mode.
    outputs = []
    with torch.enable_grad():
        for model in load_models():
            output = model(atoms_pos=data.atoms_pos.detach().clone(), **arguments)
            outputs.append(output.detach())
            del output
    hi, hij, dp = outputs
    if not all(torch.isfinite(output).all() for output in outputs):
        raise ValueError('The model could not produce a finite prediction for this conformer.')
    linear = np.linalg.matrix_rank(positions - positions.mean(axis=0), tol=1e-4) <= 1
    freq, modes = hessfreq(hi, hij, edges, atom_masses[data.atoms_x], linear=linear)
    activity = get_raman_act(chain_rule_raman(dp, modes))
    x, y = freqaraman2spec(freq, activity)
    if not np.isfinite(y).all() or float(y.max()) <= 0:
        raise ValueError('The model could not produce a valid Raman spectrum for this molecule.')
    y = y / y.max()
    return {
        'wavenumber': x.tolist(), 'intensity': y.tolist(),
        'molecule': describe_molecule(mol),
        'settings': {'range': [500, 4000], 'points': 3501, 'frequency_scale': 0.965,
                     'lorentzian_fwhm': 12, 'temperature': 298, 'laser_nm': 532, 'normalized': True},
    }
