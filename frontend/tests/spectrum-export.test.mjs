import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {createZip} from '../src/zipArchive.js';
import {spectrumText,safeSpectrumStem,spectrumExportTargets} from '../src/spectrumExport.js';

test('ZIP archive is readable with Python zipfile, preserves Unicode/binary and valid CRC', async () => {
  const zip = createZip([{name:'001_蔗糖/蔗糖_processed_V1.txt',data:'RamanShift(cm^-1)\tIntensity\n400\t1.1234567890123457\n'}, {name:'binary.png',data:new Uint8Array([0,1,255,128,3])}]);
  const candidate=fileURLToPath(new URL('../../.venv/Scripts/python.exe',import.meta.url));
  const python=process.env.RAMANCLOUD_TEST_PYTHON || (existsSync(candidate)?candidate:'python3');
  const result=spawnSync(python,['-c','import io,json,sys,zipfile; z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())); print(json.dumps({"bad":z.testzip(),"names":z.namelist(),"text":z.read(z.namelist()[0]).decode(),"binary":list(z.read("binary.png"))}))'],{input:Buffer.from(await zip.arrayBuffer())});
  assert.equal(result.status,0,result.stderr?.toString());
  const read=JSON.parse(result.stdout.toString());
  assert.equal(read.bad,null);assert.equal(read.names[0],'001_蔗糖/蔗糖_processed_V1.txt');
  assert.match(read.text,/1\.1234567890123457/);assert.deepEqual(read.binary,[0,1,255,128,3]);
});
test('unsafe archive paths and duplicates are rejected; duplicate spectrum basenames stay safe', () => {
  for(const name of ['../bad.txt','/bad.txt','C:/bad.txt','a\\b.txt']) assert.throws(()=>createZip([{name,data:'bad'}]));
  assert.throws(()=>createZip([{name:'a.txt',data:'1'},{name:'a.txt',data:'2'}]));
  assert.equal(safeSpectrumStem('folder/样本:测试.txt'),'样本_测试');
  assert.equal(safeSpectrumStem('..'),'spectrum');
});
test('TXT export keeps full paired values and matches the single export format', () => {
  assert.equal(spectrumText({wavenumber:[400.1234567890123,401],intensity:[1.1234567890123457,-1e-12]}),'RamanShift(cm^-1)\tIntensity\n400.1234567890123\t1.1234567890123457\n401\t-1e-12\n');
});
test('one completed version per checked spectrum is exported; selected older version takes precedence', () => {
  const records=[{id:'v1',analysis_type:'spectrum',created_at:'2026-11-04',result:{ai_workflow_id:'a'}},{id:'v2',analysis_type:'spectrum',created_at:'2026-11-05',result:{ai_workflow_id:'a'}},{id:'draft',analysis_type:'spectrum',kind:'workflow',workflow_id:'b'}, {id:'fallback',analysis_type:'spectrum',kind:'workflow',workflow_id:'c',version_id:'old',result_available:true}, {id:'invalid',analysis_type:'spectrum',kind:'batch_item'},{id:'other',analysis_type:'library_matching'}];
  assert.deepEqual(spectrumExportTargets(records),[{run_id:'v2'},{workflow_id:'b'},{workflow_id:'c',version_id:'old'}]);
  assert.equal(spectrumExportTargets(records,'v1')[0].run_id,'v1');
});
