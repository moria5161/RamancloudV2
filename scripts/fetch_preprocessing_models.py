"""Fetch the author's public F2P checkpoint without redistributing it in Git."""
import argparse
import hashlib
import os
from pathlib import Path
from urllib.request import build_opener, ProxyHandler

REVISION='140d056f342ebccb66b6ae052150821acc207c87'
SHA256='965cec230ea52a7094a068629b9f32a2ef3efeb6342729d47e7f7a02c7899293'
BASE='https://huggingface.co/moria5161/fast2peak/resolve/'+REVISION+'/checkpoints/f2p/'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy')
    args=parser.parse_args()
    target=Path(__file__).resolve().parents[1]/'.runtime/preprocessing-models/f2p'
    target.mkdir(parents=True,exist_ok=True)
    model=target/'best_checkpoint.pth'
    opener=build_opener(ProxyHandler({'https':args.proxy,'http':args.proxy})) if args.proxy else build_opener()
    if not model.is_file() or hashlib.sha256(model.read_bytes()).hexdigest()!=SHA256:
        temporary=model.with_suffix('.part')
        try:
            digest=hashlib.sha256()
            with opener.open(BASE+'best_checkpoint.pth',timeout=90) as response,temporary.open('wb') as output:
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    digest.update(chunk);output.write(chunk)
            if digest.hexdigest()!=SHA256:raise RuntimeError('F2P checkpoint checksum mismatch')
            os.replace(temporary,model)
        finally:
            if temporary.exists():temporary.unlink()
    if not (target/'config.yaml').is_file():
        (target/'config.yaml').write_bytes(opener.open(BASE+'config.yaml',timeout=30).read())
    print('Author F2P checkpoint verified. Source: https://huggingface.co/moria5161/fast2peak')


if __name__=='__main__':main()
