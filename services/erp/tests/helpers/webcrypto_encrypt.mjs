import { webcrypto } from 'node:crypto';

const pem = process.env.RSA_PUBLIC_KEY ?? '';
const plaintext = process.env.RSA_PLAINTEXT ?? '';

function pemToBuffer(pemText) {
  const body = pemText
    .replace('-----BEGIN PUBLIC KEY-----', '')
    .replace('-----END PUBLIC KEY-----', '')
    .replace(/\s/g, '');
  return Buffer.from(body, 'base64');
}

const key = await webcrypto.subtle.importKey(
  'spki',
  pemToBuffer(pem),
  { name: 'RSA-OAEP', hash: 'SHA-256' },
  false,
  ['encrypt'],
);
const cipher = await webcrypto.subtle.encrypt(
  { name: 'RSA-OAEP' },
  key,
  new TextEncoder().encode(plaintext),
);
process.stdout.write(Buffer.from(cipher).toString('base64'));
