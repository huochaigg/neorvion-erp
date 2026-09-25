import type { ReactNode } from 'react';
import { AppLogo } from '@/components/AppLogo';
import styles from './AuthLayout.module.scss';

interface AuthLayoutProps {
  title: string;
  description: string;
  children: ReactNode;
}

export function AuthLayout({ title, description, children }: AuthLayoutProps) {
  return (
    <div className={styles.page}>
      <section className={styles.brand}>
        <AppLogo />
        <h1 className={styles.headline}>{title}</h1>
        <p className={styles.desc}>{description}</p>
      </section>
      <section className={styles.formPane}>{children}</section>
    </div>
  );
}
