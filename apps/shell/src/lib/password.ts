/** 浏览器 Web Crypto 计算 SHA-256，请求体不携带明文密码。 */
export async function digestPassword(plainPassword: string): Promise<string> {
  const bytes = new TextEncoder().encode(plainPassword);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}
