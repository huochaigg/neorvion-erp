const storageKey = (name: string) => `neorvion:micro:last:${name}`;

function withSessionStorage<T>(fn: (storage: Storage) => T, fallback: T): T {
  try {
    const storage = globalThis.sessionStorage;
    if (!storage) {
      return fallback;
    }
    return fn(storage);
  } catch {
    return fallback;
  }
}

export function getLastMicroHref(name: string): string | null {
  return withSessionStorage((storage) => storage.getItem(storageKey(name)), null);
}

export function setLastMicroHref(name: string, href: string) {
  withSessionStorage((storage) => {
    storage.setItem(storageKey(name), href);
    return undefined;
  }, undefined);
}

export function clearLastMicroHref(name: string) {
  withSessionStorage((storage) => {
    storage.removeItem(storageKey(name));
    return undefined;
  }, undefined);
}

export function clearAllLastMicroHrefs() {
  withSessionStorage((storage) => {
    const prefix = 'neorvion:micro:last:';
    const keys: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key?.startsWith(prefix)) {
        keys.push(key);
      }
    }
    keys.forEach((key) => storage.removeItem(key));
    return undefined;
  }, undefined);
}
