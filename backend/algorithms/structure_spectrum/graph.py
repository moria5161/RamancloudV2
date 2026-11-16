"""Molecular graph features preserved from the original spectral prediction model."""
from math import pi
import numpy as np
import torch
from rdkit import Chem
from torch_geometric.data import Data
from torch_geometric.nn import radius_graph

def rdmol2x_pos(rdmol):
    atoms_x = np.zeros(shape = [rdmol.GetNumAtoms()],dtype=np.int64)
    atoms_pos = np.zeros(shape = [rdmol.GetNumAtoms(),3],dtype=np.float32)
    confer = rdmol.GetConformer()
    for i in range(rdmol.GetNumAtoms()):
        atom = rdmol.GetAtomWithIdx(i)
        atoms_x[i] = atom.GetAtomicNum()
        atoms_pos[i] = np.array([confer.GetAtomPosition(i).x,confer.GetAtomPosition(i).y,confer.GetAtomPosition(i).z],dtype=np.float32)
    return atoms_x,atoms_pos

def generate_atoms_edge_index(atoms_adjacent_matrix: np.array = None,
                              mol:Chem.rdchem.Mol = None):
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # 按照化学键遍历
    # if np.where(atoms_adjacent_matrix==0)[0].shape[0] != atoms_adjacent_matrix.shape[0]:
    #     return KeyError
    edge_index = np.zeros(shape=[1,4],dtype=np.int32)
    for i in range(mol.GetNumBonds()):
        # BeginAtomIdx
        atom_mid_1 = mol.GetBondWithIdx(i).GetBeginAtomIdx()
        # EndAtomIdx
        atom_mid_2 = mol.GetBondWithIdx(i).GetEndAtomIdx()
        atom_head = np.where(atoms_adjacent_matrix[atom_mid_1]==1)[0]
        atom_tail = np.where(atoms_adjacent_matrix[atom_mid_2]==1)[0]
        for j in range(atom_head.shape[0]):
            if atom_head[j] == atom_mid_2:
                continue
            for k in range(atom_tail.shape[0]):
                if atom_tail[k] == atom_mid_1:
                    continue  
                edge_index = np.r_[edge_index,np.array([[atom_head[j],atom_mid_1,atom_mid_2,atom_tail[k]]],dtype=np.int16)]
                edge_index = np.r_[edge_index,np.array([[atom_tail[k],atom_mid_2,atom_mid_1,atom_head[j]]],dtype=np.int16)]
    
    return edge_index[1:]

def atoms2bonds_edge_index(atoms_edge_index: np.array = None,
                            mol: Chem.rdchem.Mol = None):
    bond_type = [
        'SINGLE',
        'DOUBLE',
        'TRIPLE',
        'AROMATIC'
    ]
    bonds_edge_index = np.zeros(shape=[atoms_edge_index.shape[0],3],dtype=np.int32)
    bonds_x = np.zeros(shape=[mol.GetNumBonds(),4],dtype=np.float32)
    atom_distance = Chem.Get3DDistanceMatrix(mol)
    for i in range(mol.GetNumBonds()):
        bonds_x[i,0] = mol.GetBondWithIdx(i).GetBeginAtomIdx()
        bonds_x[i,1] = mol.GetBondWithIdx(i).GetEndAtomIdx()
        bonds_x[i,2] = bond_type.index(mol.GetBondWithIdx(i).GetBondType().name)
        bonds_x[i,0] = atom_distance[mol.GetBondWithIdx(i).GetBeginAtomIdx(),
                                    mol.GetBondWithIdx(i).GetEndAtomIdx()]
    for i in range(atoms_edge_index.shape[0]):
        for j in range(atoms_edge_index.shape[1]-1):
            bonds_edge_index[i,j] = mol.GetBondBetweenAtoms(int(atoms_edge_index[i,j]),
                                                            int(atoms_edge_index[i,j+1])).GetIdx()
    return bonds_edge_index,bonds_x

def generate_angel_edge_bondes(atoms_pos: np.array = None,
                             atoms_edge_index: np.array = None):
    angle_edge_bonds = np.zeros(shape=[atoms_edge_index.shape[0],4],dtype=np.float32)
    for i in range(atoms_edge_index.shape[0]):
        bond_1 = atoms_pos[atoms_edge_index[i,1]] - atoms_pos[atoms_edge_index[i,0]]
        bond_2 = atoms_pos[atoms_edge_index[i,2]] - atoms_pos[atoms_edge_index[i,1]]
        bond_3 = atoms_pos[atoms_edge_index[i,3]] - atoms_pos[atoms_edge_index[i,2]]
        # 1-2的夹角余弦
        angle_edge_bonds[i,0] = np.arccos(np.clip(np.dot(bond_1,bond_2) / np.linalg.norm(bond_1) /np.linalg.norm(bond_2), -1, 1))/pi
        # 2-3的夹角余弦
        angle_edge_bonds[i,1] = np.arccos(np.clip(np.dot(bond_2,bond_3) / np.linalg.norm(bond_2) /np.linalg.norm(bond_3), -1, 1))/pi
        # 1-3的夹角余弦,特别的需要为其添加<+,-,0>三种符号实现唯一区分
        angle_edge_bonds[i,2] = np.arccos(np.clip(np.dot(bond_1,bond_3) / np.linalg.norm(bond_1) /np.linalg.norm(bond_3), -1, 1))/pi
        temp = np.dot(np.cross(bond_1,bond_2),bond_3)
        if temp == 0:
           angle_edge_bonds[i,3] =  1
        else:
           angle_edge_bonds[i,3] =  int(temp /abs(temp) + 1) 

    return angle_edge_bonds

def Is_bonds_edge_index(bonds_edge_index,bonds_x):
    if int(bonds_x.shape[0]) - 1 == int(np.max(bonds_edge_index[:,2])):
        return True
    else :
        return False

def generate_data(atomicNumList, xyz_coordinates,rdmol,matrix_mol):
    atoms_edge_index = generate_atoms_edge_index(matrix_mol,rdmol)
    bonds_edge_index,bonds_x = atoms2bonds_edge_index(atoms_edge_index,rdmol)
    if not len(bonds_edge_index) or not Is_bonds_edge_index(bonds_edge_index,bonds_x):
        raise ValueError('This model requires connected four-atom bond paths. Try a larger molecule.')
    angle_edge_bonds = generate_angel_edge_bondes(xyz_coordinates,atoms_edge_index)
    if not np.isfinite(angle_edge_bonds).all():
        raise ValueError('Invalid molecular geometry. Check atomic coordinates.')
    bonds_edge_attr = np.c_[atoms_edge_index[:,1:3],bonds_x[bonds_edge_index[:,1]][:,2:]]
    bonds_edge_attr = np.c_[bonds_edge_attr,angle_edge_bonds]

    atomicNumList = torch.tensor(atomicNumList,dtype=torch.long)
    xyz_coordinates = torch.tensor(xyz_coordinates,dtype=torch.float32)
    bonds_x = torch.tensor(bonds_x,dtype=torch.float32)
    bonds_edge_index = torch.tensor(bonds_edge_index,dtype=torch.long)
    bonds_edge_attr = torch.tensor(bonds_edge_attr,dtype=torch.float32)
    # group = torch.tensor(group,dtype=torch.float32)
    return atomicNumList,xyz_coordinates,bonds_x,bonds_edge_index,bonds_edge_attr

def rdmol2pt(rdmol:Chem.rdchem.Mol,name:str):
    
    atoms_x,atoms_pos = rdmol2x_pos(rdmol)
    AC = Chem.GetAdjacencyMatrix(rdmol)
    atoms_x,atoms_pos,bonds_x,bonds_edge_index,bonds_edge_attr  = generate_data(atoms_x,atoms_pos,rdmol,AC)
    atoms_edge_index = radius_graph(x=atoms_pos,r=5.0,batch=torch.zeros_like(atoms_x,dtype=torch.long)) 
    atoms_count = torch.tensor([[atoms_x.shape[0],atoms_edge_index.shape[1],rdmol.GetNumAtoms()]],dtype = torch.long)
    data = Data(       x = bonds_x,    edge_attr = bonds_edge_attr,
                        edge_index = bonds_edge_index.T, atoms_pos = atoms_pos, 
                        atoms_x = atoms_x, atoms_count = atoms_count,
                        name = name
                        
                        )
    return data
