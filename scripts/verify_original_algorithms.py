"""Compare the current pipeline with an independently imported local original tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import numpy as np
import legacy_algorithms as legacy

REFERENCE = r'''
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, sys.argv[1])
from algorithms import processing as p
directory=Path(sys.argv[2])
matrix=np.load(directory/'input.npy',allow_pickle=False)
catalog=json.loads((directory/'catalog.json').read_text())
outputs={}
for spec in catalog:
    method=spec['method']
    params={key:rule[0] for key,rule in p.PARAMETERS[method].items()}
    for label,data in [('single',matrix[:1]),('matrix',matrix)]:
        if spec['type']=='denoise':
            out=p.denoise_batch(data,params,method); baseline=None
        else:out,baseline=p.correct_baseline_batch(data,params,method)
        outputs[method+'_'+label]=out
        if baseline is not None:outputs[method+'_'+label+'_baseline']=baseline
np.savez(directory/'reference.npz',**outputs)
metadata={method:{key:{'default':rule[0],'min':rule[2],'max':rule[3]} for key,rule in rules.items()} for method,rules in p.PARAMETERS.items()}
(directory/'parameters.json').write_text(json.dumps(metadata))
'''


def verify(original, output):
    original = original.resolve()
    manifest=json.loads((ROOT/'backend/vendor/legacy_v2/SOURCE.json').read_text())
    hashes=[]
    for relative in manifest['files']:
        reference=original/'backend/algorithms'/relative
        current=ROOT/'backend/vendor/legacy_v2'/relative
        identical=reference.is_file() and hashlib.sha256(reference.read_bytes()).digest()==hashlib.sha256(current.read_bytes()).digest()
        hashes.append({'file':relative,'identical':identical})
    if not all(row['identical'] for row in hashes):
        raise AssertionError('Original source differs: '+str([row for row in hashes if not row['identical']]))
    x=np.linspace(200,2000,256)
    y=100+.02*x+300*np.exp(-((x-1004)/25)**2)+np.sin(x/13)
    matrix=np.stack([y,1.1*y+3,.8*y+6])
    environment=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',
                     RAMANCLOUD_F2P_MODEL=str(legacy.model_path('f2p')),
                     RAMANCLOUD_AIRNET_MODEL=str(legacy.model_path('airnet')))
    results=[]
    with tempfile.TemporaryDirectory(prefix='raman-parity-') as name:
        directory=Path(name)
        np.save(directory/'input.npy',matrix,allow_pickle=False)
        (directory/'catalog.json').write_text(json.dumps(legacy.CATALOG),encoding='utf-8')
        (directory/'reference.py').write_text(REFERENCE,encoding='utf-8')
        subprocess.run([str(legacy.python_path()),str(directory/'reference.py'),str(original/'backend'),name],env=environment,check=True,timeout=600)
        defaults=json.loads((directory/'parameters.json').read_text())
        import app
        with np.load(directory/'reference.npz',allow_pickle=False) as reference:
            for spec in legacy.CATALOG:
                method=spec['method'];params={key:rule['default'] for key,rule in spec['params'].items()}
                assert set(spec['params'])==set(defaults[method]),method
                for key,rule in spec['params'].items():
                    assert rule['default']==defaults[method][key]['default'],(method,key)
                    if 'options' not in rule:
                        assert rule['min']==defaults[method][key]['min'] and rule['max']==defaults[method][key]['max'],(method,key)
                record={'method':method,'parameters_identical':True}
                for label,data in [('single',matrix[0]),('matrix',matrix)]:
                    _,out,baseline,_=app.apply_pipeline(x,data,[app.Step(type=spec['type'],method=method,params=params)])
                    expected=reference[method+'_'+label].reshape(data.shape)
                    np.testing.assert_allclose(out,expected,rtol=1e-6,atol=1e-6,err_msg=method+' '+label)
                    assert np.isfinite(out).all()
                    record[label+'_max_abs_error']=float(np.max(np.abs(out-expected)))
                    if spec['type']=='baseline':
                        np.testing.assert_allclose(baseline,reference[method+'_'+label+'_baseline'].reshape(data.shape),rtol=1e-6,atol=1e-6)
                results.append(record)
                print(json.dumps(record),flush=True)
    report={'original':str(original),'source_files':hashes,'tolerance':{'rtol':1e-6,'atol':1e-6},'algorithms':results,'passed':True}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: independent source, parameters, single/matrix and baseline parity')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'logs/original-algorithm-parity.json')
    args=parser.parse_args()
    verify(args.original,args.output)
