import Link from 'next/link';
import { Home } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { getTranslations } from 'next-intl/server';

export default async function NotFound() {
  const t = await getTranslations('common');

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="text-center max-w-md">
        <h1 className="text-8xl font-bold text-muted-foreground mb-4">{t('notFoundCode')}</h1>
        <h2 className="text-2xl font-semibold mb-2">{t('notFound')}</h2>
        <p className="text-muted-foreground mb-6">
          {t('notFoundDescription')}
        </p>
        <Button asChild>
          <Link href="/dashboard">
            <Home className="w-4 h-4 mr-2" />
            {t('backToDashboard')}
          </Link>
        </Button>
      </div>
    </div>
  );
}
