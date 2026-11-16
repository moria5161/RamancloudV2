import test from 'node:test';
import assert from 'node:assert/strict';
import { requestErrorDetail } from './requestError.js';

test('JSON and Blob errors retain the server explanation', async () => {
  assert.equal(await requestErrorDetail({ response: { data: { detail: 'Invalid coordinates' } } }), 'Invalid coordinates');
  assert.equal(await requestErrorDetail({ response: { data: new Blob([JSON.stringify({ detail: 'Invalid coordinates' })]) } }), 'Invalid coordinates');
});
test('non-JSON errors fall back without rendering HTML', async () => {
  assert.equal(await requestErrorDetail({ response: { data: new Blob(['<html>502</html>']) } }), '');
  assert.equal(await requestErrorDetail(new Error('Network error')), '');
});
