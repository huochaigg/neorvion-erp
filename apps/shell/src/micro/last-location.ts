const storageKey = (name: string) => `neorvion:micro:last:${name}`;

export function getLastMicroHref(name: string): string | null {
  try {
    return sessionStorage.getItem(storageKey(name));
  } catch {
    return null;
  }
}

export function setLastMicroHref(name: string, href: string) {
  try {
    sessionStorage.setItem(storageKey(name), href);
  } catch {
    // 隐私模式等无法写入时，仅影响「从入口恢复上次路由」。
  }
}

export function clearLastMicroHref(name: string) {
  try {
    sessionStorage.removeItem(storageKey(name));
  } catch {
    // ignore
  }
}

export function clearAllLastMicroHrefs() {
  try {
    const prefix = 'neorvion:micro:last:';
    const keys: string[] = [];
    for (let index = 0; index < sessionStorage.length; index += 1) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(prefix)) {
        keys.push(key);
      }
    }
    keys.forEach((key) => sessionStorage.removeItem(key));
  } catch {
    // ignore
  }
}
