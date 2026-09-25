import type { ApiResponse, AuthPublicKey, EncryptedPasswordPayload } from '@neorvion/shared';
import { apiClient, unwrapApi } from '@/api/client';

function pemToArrayBuffer(pem: string): ArrayBuffer {
  const body = pem
    .replace('-----BEGIN PUBLIC KEY-----', '')
    .replace('-----END PUBLIC KEY-----', '')
    .replace(/\s/g, '');
  const binary = atob(body);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

async function fetchAuthPublicKey(): Promise<AuthPublicKey> {
  return unwrapApi(apiClient.get<ApiResponse<AuthPublicKey>>('/api/v1/auth/public-key'));
}

async function encryptWithPublicKey(plainPassword: string, publicKeyPem: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'spki',
    pemToArrayBuffer(publicKeyPem),
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt'],
  );
  const cipher = await crypto.subtle.encrypt(
    { name: 'RSA-OAEP' },
    key,
    new TextEncoder().encode(plainPassword),
  );
  return arrayBufferToBase64(cipher);
}

/**
 * 获取一次性公钥并加密密码。明文只存在于本次调用栈，不写入任何存储。
 * 不要把明文或密文打印到控制台。
 */
export async function encryptAuthPassword(plainPassword: string): Promise<EncryptedPasswordPayload> {
  const material = await fetchAuthPublicKey();
  const encryptedPassword = await encryptWithPublicKey(plainPassword, material.public_key);
  return {
    encrypted_password: encryptedPassword,
    key_id: material.key_id,
    challenge_id: material.challenge_id,
  };
}
