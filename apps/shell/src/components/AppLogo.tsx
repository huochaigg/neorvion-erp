import styles from './AppLogo.module.scss';

interface AppLogoProps {
  compact?: boolean;
}

export function AppLogo({ compact = false }: AppLogoProps) {
  return (
    <div className="flex items-center gap-2">
      <span className={styles.mark}>N</span>
      {compact ? null : (
        <span className={styles.wordmark}>
          <span className={styles.title}>Neorvion ERP</span>
          <span className={styles.subtitle}>跨境供应链</span>
        </span>
      )}
    </div>
  );
}
