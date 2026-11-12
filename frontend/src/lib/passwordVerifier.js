// Salted PBKDF2 verifier used by the lock screen. The plaintext password is never
// stored; only a random salt and the derived hash are, so a reload can still check
// an unlock attempt. This is a client-side stopgap until the backend can verify
// passwords. It needs a secure context (https or localhost) for crypto.subtle.

const ITERATIONS = 150000;
const SALT_BYTES = 16;
const HASH_BITS = 256;

const toBase64 = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes)));
const fromBase64 = (text) => Uint8Array.from(atob(text), (c) => c.charCodeAt(0));

const derive = async (password, salt, iterations) => {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new Error('Web Crypto is unavailable (a secure context is required).');

  const key = await subtle.importKey(
    'raw',
    new TextEncoder().encode(password),
    'PBKDF2',
    false,
    ['deriveBits'],
  );
  return subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations }, key, HASH_BITS);
};

export const createPasswordVerifier = async (password) => {
  const salt = globalThis.crypto.getRandomValues(new Uint8Array(SALT_BYTES));
  const hash = await derive(password, salt, ITERATIONS);
  return { salt: toBase64(salt), hash: toBase64(hash), iterations: ITERATIONS };
};

export const verifyPassword = async (password, verifier) => {
  if (!verifier?.salt || !verifier?.hash || !verifier?.iterations) return false;

  try {
    const hash = new Uint8Array(
      await derive(password, fromBase64(verifier.salt), verifier.iterations),
    );
    const expected = fromBase64(verifier.hash);
    if (hash.length !== expected.length) return false;

    // Compare every byte so timing does not reveal where the hashes differ.
    let diff = 0;
    for (let i = 0; i < hash.length; i += 1) diff |= hash[i] ^ expected[i];
    return diff === 0;
  } catch {
    return false;
  }
};
