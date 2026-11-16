"""Non-destructive HTTP checks using only a tiny self-uploaded, unarchived fixture."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

import httpx


def verify(base, api_prefix='ramancloud-api'):
    base = base.rstrip('/')
    api = api_prefix.strip('/')
    results = []
    identifiers = []
    payload = b'\t\t100\t200\t300\t400\t500\t600\t700\t800\n0\t0\t1\t2\t4\t3\t6\t5\t7\t8\n'
    with httpx.Client(base_url=base + '/', timeout=30, trust_env=False) as owner, \
            httpx.Client(base_url=base + '/', timeout=30, trust_env=False) as other, \
            httpx.Client(base_url=base + '/', timeout=30, trust_env=False) as anonymous:
        def check(name, response, status):
            if response.status_code != status:
                raise RuntimeError(f'{name}: expected {status}, got {response.status_code}: {response.text[:200]}')
            results.append({'check': name, 'status': status, 'passed': True})
            return response

        homepage = check('Public homepage', anonymous.get(''), 200)
        for header, expected in (
            ('x-content-type-options', 'nosniff'), ('x-frame-options', 'SAMEORIGIN'),
            ('referrer-policy', 'strict-origin-when-cross-origin'),
        ):
            if homepage.headers.get(header) != expected:
                raise RuntimeError(f'Missing or incorrect browser security header: {header}')
            results.append({'check': header, 'passed': True})
        policy = homepage.headers.get('content-security-policy', '')
        if "frame-ancestors 'self'" not in policy or "'unsafe-eval'" in policy:
            raise RuntimeError('Main document CSP is missing or permits string evaluation')
        results.append({'check': 'Main document CSP enforced', 'passed': True})
        for path in ('.env', '.git/config', 'backend/app.py', 'uploads.sqlite3', 'assets/.env'):
            check(f'Sensitive path blocked: {path}', anonymous.get(path), 404)
        check('Public health', anonymous.get(f'{api}/health'), 200)
        check('Public aggregate statistics', anonymous.get(f'{api}/visits/summary'), 200)
        check('Anonymous upload denied', anonymous.post(f'{api}/upload-hyperspectral',
              files={'file': ('security-check.txt', payload)}, data={'share_data': 'false'}), 401)
        headers = {'X-RamanCloud-CSRF': check('Owner session', owner.get(f'{api}/session'), 200).json()['csrf_token']}
        other_headers = {'X-RamanCloud-CSRF': check('Other session', other.get(f'{api}/session'), 200).json()['csrf_token']}
        check('Missing CSRF denied', owner.post(f'{api}/process', json={}), 403)
        check('Cross-site access denied', owner.get(f'{api}/session', headers={'Origin': 'https://invalid.example'}), 403)
        form_headers = {**headers, 'Content-Type': 'application/x-www-form-urlencoded'}
        check('Oversized text form rejected before parsing', owner.post(f'{api}/structure/conformer',
              headers=form_headers, content='smiles=' + 'C' * (64 * 1024)), 413)
        check('Excessive text form fields rejected', owner.post(f'{api}/structure/conformer',
              headers=form_headers, content='&'.join(f'f{i}=x' for i in range(1001))), 400)
        response = check('Own upload accepted', owner.post(f'{api}/upload-hyperspectral', headers=headers,
                         files={'file': (f'security-check-{uuid4().hex}.txt', payload)},
                         data={'share_data': 'false', 'mode': 'imaging', 'instrument': 'Horiba'}), 200)
        dataset_id = response.json()['data']['dataset_id']
        identifiers.append(dataset_id)
        request = {'dataset_id': dataset_id, 'wavenumber': list(range(100, 801, 100)), 'format': 'mapping'}
        try:
            check('Own pixel readable', owner.get(f'{api}/hyperspectral-pixel/{dataset_id}'), 200)
            check('Cross-session pixel denied', other.get(f'{api}/hyperspectral-pixel/{dataset_id}'), 404)
            check('Cross-session slice denied', other.get(f'{api}/hyperspectral-slice/{dataset_id}'), 404)
            check('Cross-session download denied', other.post(f'{api}/download', headers=other_headers, json=request), 404)
            check('Cross-session processing denied', other.post(f'{api}/process-hyperspectral', headers=other_headers, json=request), 404)
            check('Cross-session delete denied', other.delete(f'{api}/datasets/{dataset_id}', headers=other_headers), 404)
            check('Own download accepted', owner.post(f'{api}/download', headers=headers, json=request), 200)
            processed = check('Own SG and baseline processing accepted', owner.post(f'{api}/process-hyperspectral',
                              headers=headers, json={**request, 'steps': [
                                  {'type': 'denoise', 'method': 'sg', 'params': {'window_size': 7, 'order': 3}},
                                  {'type': 'baseline', 'method': 'imodpoly', 'params': {'poly_order': 2}},
                              ]}), 200).json()['data']
            identifiers.extend([processed['processed_dataset_id'], processed['baseline_dataset_id']])
            for label, identifier in [('Processed', identifiers[1]), ('Baseline', identifiers[2])]:
                check(f'{label} owner can read', owner.get(f'{api}/hyperspectral-pixel/{identifier}'), 200)
                check(f'{label} cross-session read denied', other.get(f'{api}/hyperspectral-pixel/{identifier}'), 404)
            check('Unknown dataset delete denied', owner.delete(f'{api}/datasets/{uuid4().hex}', headers=headers), 404)
        finally:
            for identifier in identifiers:
                check('Self-uploaded test dataset released', owner.delete(f'{api}/datasets/{identifier}', headers=headers), 200)
        check('Deleted test dataset unavailable', owner.get(f'{api}/hyperspectral-pixel/{dataset_id}'), 404)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--api-prefix', default='ramancloud-api')
    parser.add_argument('--output', type=Path)
    options = parser.parse_args()
    results = verify(options.base_url, options.api_prefix)
    failed = sum(not result['passed'] for result in results)
    report = {'base_url': options.base_url, 'passed': len(results) - failed, 'failed': failed, 'checks': results}
    if options.output:
        options.output.write_text(json.dumps(report, indent=2) + '\n')
        options.output.chmod(0o600)
    print(json.dumps(report, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
