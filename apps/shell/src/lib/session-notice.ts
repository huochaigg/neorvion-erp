let pendingNotice: string | null = null;

export function queueAuthNotice(message: string) {
  pendingNotice = message;
}

export function consumePendingAuthNotice(): string | null {
  const notice = pendingNotice;
  pendingNotice = null;
  return notice;
}
