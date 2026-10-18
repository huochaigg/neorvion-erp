import styles from './StatusTag.module.scss';

interface StatusTagProps {
  tone?: 'ready' | 'pending';
  children: string;
}

export function StatusTag({ tone = 'pending', children }: StatusTagProps) {
  return <span className={`${styles.tag} ${styles[tone]}`}>{children}</span>;
}
