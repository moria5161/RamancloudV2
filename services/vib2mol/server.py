"""Private loopback worker; uses the official architecture and two verified weights."""
import argparse
import base64
import hashlib
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONFIG = json.loads(os.environ['RAMANCLOUD_VIB2MOL_CONFIG'])
PROFILE, PATHS = CONFIG['profile'], CONFIG['paths']
TOKEN = os.environ['RAMANCLOUD_VIB2MOL_TOKEN']
sys.path.insert(0, PATHS['source'])
LOCK = threading.Lock()
MODELS = {}
AGENT_VERIFIED = False


def verify_agent():
    global AGENT_VERIFIED
    if AGENT_VERIFIED:
        return
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
    from vib2mol_agent_package import installed_agent, package_hash
    manifest = installed_agent(PATHS['source'])
    if not manifest or manifest['package_sha256'] != PROFILE.get('agent_package_sha256'):
        raise ValueError('Agent 版本与任务记录不一致，请重新安装扩展。')
    if package_hash(Path(PATHS['source']) / 'vib2mol_agent') != manifest['package_sha256']:
        raise ValueError('Agent 文件校验失败；请保留本地修改并重新安装经过验证的扩展。')
    AGENT_VERIFIED = True


def load_model(name):
    if name not in MODELS:
        import torch
        from models import build_model
        path = Path(PATHS[name])
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != PROFILE[f'{name}_sha256']:
            raise ValueError(f'{name} 权重校验失败，请重新下载。')
        torch.set_num_threads(PROFILE['threads'])
        model = build_model('vib2mol', spectral_channel=1)
        state = torch.load(path, map_location='cpu', weights_only=True)
        state = {key.removeprefix('module.'): value for key, value in state.items()}
        model.load_state_dict(state, strict=True)
        model.eval().to(PROFILE['device'])
        MODELS[name] = model
    return MODELS[name]


def predict(payload):
    import numpy as np
    import torch
    # Set this in every request thread. On this Windows CPU, multi-threaded
    # reductions with torch 2.4 produced inconsistent values for identical tensors.
    torch.set_num_threads(PROFILE['threads'])
    from transformers import AutoTokenizer
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Draw, rdMolDescriptors
    RDLogger.DisableLog('rdApp.*')
    tokenizer = AutoTokenizer.from_pretrained(str(Path(PATHS['source']) / 'models/MolTokenizer'), local_files_only=True)
    values = np.asarray(payload['intensity'], dtype=np.float32)
    if values.shape != (PROFILE['points'],) or not np.isfinite(values).all():
        raise ValueError('模型输入网格无效。')
    started = time.monotonic()
    is_agent = PROFILE.get('engine') == 'agent'
    if is_agent:
        verify_agent()
    tensor = torch.tensor(values, device=PROFILE['device']).reshape(1, 1, -1)
    model = load_model('generation')
    with torch.inference_mode():
        output = model.beam_infer_lm({'raman': tensor}, max_len=PROFILE['max_tokens'],
                                    beam_size=PROFILE['beam_size'], temperature=PROFILE['temperature'])
    candidates, seen = [], set()
    dropped = dict(invalid=0, duplicate=0, truncated=0, formula=0)
    for ids, score in zip(output['pred_ids'][0], output['score'][0]):
        tokens = ids.detach().cpu().tolist()
        if 2 not in tokens:
            dropped['truncated'] += 1
            continue
        text = tokenizer.decode(tokens, skip_special_tokens=False).split('</s>')[0].replace('<s>', '').strip()
        mol = Chem.MolFromSmiles(text)
        if not mol or mol.GetNumAtoms() == 0 or any(atom.GetAtomicNum() == 0 for atom in mol.GetAtoms()):
            dropped['invalid'] += 1
            continue
        key = Chem.MolToInchiKey(mol)
        canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=False)
        if key in seen:
            dropped['duplicate'] += 1
            continue
        seen.add(key)
        formula = rdMolDescriptors.CalcMolFormula(mol)
        import re
        counts = {element: int(count or 1) for element, count in re.findall(r'([A-Z][a-z]?)([0-9]*)', formula)}
        if not is_agent and payload.get('formula_counts') and counts != payload['formula_counts']:
            dropped['formula'] += 1
            continue
        candidates.append(dict(smiles=canonical, formula=formula, inchikey=key, generation_score=float(score),
                               matching_score=None, _mol=mol,
                               _kekule=Chem.MolToSmiles(mol, canonical=True, isomericSmiles=False, kekuleSmiles=True)))
    if payload.get('rerank') and candidates:
        rank_model = load_model('matching')
        with torch.inference_mode():
            for candidate in candidates:
                encoded = tokenizer(candidate['_kekule'], padding=True, return_tensors='pt', truncation=False)
                encoded = {key: value.to(PROFILE['device']) for key, value in encoded.items()}
                logits = rank_model.matching({'raman': tensor, 'smiles': encoded})
                candidate['matching_score'] = float(logits.softmax(dim=1)[0, 1].item())
        candidates.sort(key=lambda item: item['matching_score'], reverse=True)
    agent_metadata = None
    if is_agent:
        from agent_adapter import enhance
        candidates, agent_metadata, removed = enhance(candidates, values, payload, PROFILE, PATHS['source'])
        dropped['formula'] += removed
    for index, candidate in enumerate(candidates[:payload['top_k']]):
        mol = candidate.pop('_mol')
        candidate.pop('_kekule')
        drawer = Draw.MolDraw2DCairo(460, 280)
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        candidate.update(id=str(index + 1), rank=index + 1,
                         image_png=base64.b64encode(drawer.GetDrawingText()).decode(), sdf=Chem.MolToMolBlock(mol))
    return dict(candidates=candidates[:payload['top_k']], dropped=dropped, beam_size=PROFILE['beam_size'], agent=agent_metadata,
                duration_seconds=round(time.monotonic() - started, 2), inference_performed=True,
                ranking='matching_score' if payload.get('rerank') else 'generation_score')


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body):
        content = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def authorized(self):
        import hmac
        if not hmac.compare_digest(self.headers.get('X-Worker-Token', ''), TOKEN):
            self.respond(403, {'error': 'Forbidden'})
            return False
        return True

    def do_GET(self):
        if self.authorized():
            self.respond(200, {'service': 'ramancloud-vib2mol', 'profile_id': PROFILE['id']})

    def do_POST(self):
        if not self.authorized():
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 100000:
                raise ValueError('Invalid request size')
            payload = json.loads(self.rfile.read(length))
            with LOCK:
                result = predict(payload)
            self.respond(200, result)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.respond(500, {'error': str(exc)[:500]})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    # Exit if the owning backend disappears, including after an interrupted reload.
    parent = os.getppid()
    def watch_parent():
        import ctypes
        if os.name == 'nt':
            from ctypes import wintypes
            kernel = ctypes.windll.kernel32
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            handle = kernel.OpenProcess(0x100000, False, parent)
            if handle:
                kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
                os._exit(0)
        else:
            while os.getppid() == parent:
                time.sleep(2)
            os._exit(0)
    threading.Thread(target=watch_parent, daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
