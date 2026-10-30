"""Bounded molecule image cache; data sources stay in tools.molecules."""
from functools import lru_cache
import io

from rdkit import Chem
from rdkit.Chem import Draw
from tools.molecules import smiles_from_pubchem


@lru_cache(maxsize=256)
def molecule_png(name=None, smiles=None):
    structure = smiles or smiles_from_pubchem(name)
    molecule = Chem.MolFromSmiles(structure)
    if molecule is None:
        raise ValueError("SMILES 解析失败")
    buffer = io.BytesIO()
    Draw.MolToImage(molecule, size=(260, 200)).save(buffer, format="PNG")
    return buffer.getvalue()
