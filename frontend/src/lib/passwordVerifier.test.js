import test from 'node:test';
import assert from 'node:assert/strict';
import { createPasswordVerifier, verifyPassword } from './passwordVerifier.js';

test('accepts the original password and rejects others', async () => {
  const verifier = await createPasswordVerifier('correct horse');

  assert.equal(await verifyPassword('correct horse', verifier), true);
  assert.equal(await verifyPassword('wrong', verifier), false);
  assert.equal(await verifyPassword('', verifier), false);
});

test('does not store the plaintext and salts every verifier', async () => {
  const a = await createPasswordVerifier('same');
  const b = await createPasswordVerifier('same');

  assert.ok(!JSON.stringify(a).includes('same'));
  assert.notEqual(a.salt, b.salt);
  assert.notEqual(a.hash, b.hash);
});

test('rejects missing or malformed verifiers', async () => {
  assert.equal(await verifyPassword('x', null), false);
  assert.equal(await verifyPassword('x', { salt: '!!', hash: '!!', iterations: 1 }), false);
});
