import { test } from 'node:test';
import assert from 'node:assert/strict';
import { apiErrorMessage } from '../src/authErrors.js';

test('string server errors remain readable', () => {
  assert.equal(apiErrorMessage({ response: { data: { detail: 'Incorrect password' } } }), 'Incorrect password');
});
test('FastAPI validation arrays become text, without exposing input values', () => {
  const error = { response: { data: { detail: [{ loc: ['body', 'username'], msg: 'Username is too short', input: 'private-input' }, { msg: 'Password is too short' }] } } };
  assert.equal(apiErrorMessage(error), 'Username is too short; Password is too short');
  assert.equal(apiErrorMessage(error).includes('private-input'), false);
});
test('nonrenderable or empty errors use the supplied fallback', () => {
  for (const detail of [[], [{ input: 'private' }], {}, null, 123, '']) {
    assert.equal(apiErrorMessage({ response: { data: { detail } } }, 'Please retry'), 'Please retry');
  }
});
test('legacy msg errors are supported', () => {
  assert.equal(apiErrorMessage({ response: { data: { msg: 'Already registered' } } }), 'Already registered');
});
test('network failures do not break the form', () => {
  assert.equal(apiErrorMessage(new Error('network failed'), 'Service unavailable'), 'Service unavailable');
});
