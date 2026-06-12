'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Home,
  Shirt,
  Sparkles,
  Layers,
  LayoutGrid,
  History,
  BarChart3,
  Brain,
  Settings,
  Users,
  Bell,
  HeartHandshake,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslations } from 'next-intl';

export function Sidebar() {
  const pathname = usePathname();
  const t = useTranslations('nav');

  const navigation = [
    { name: t('dashboard'), href: '/dashboard', icon: Home },
    { name: t('wardrobe'), href: '/dashboard/wardrobe', icon: Shirt },
    { name: t('suggestOutfit'), href: '/dashboard/suggest', icon: Sparkles },
    { name: t('outfits'), href: '/dashboard/outfits', icon: LayoutGrid },
    { name: t('pairings'), href: '/dashboard/pairings', icon: Layers },
    { name: t('history'), href: '/dashboard/history', icon: History },
    { name: t('familyFeed'), href: '/dashboard/family/feed', icon: HeartHandshake },
    { name: t('analytics'), href: '/dashboard/analytics', icon: BarChart3 },
    { name: t('aiLearning'), href: '/dashboard/learning', icon: Brain },
  ];

  const secondaryNavigation = [
    { name: t('family'), href: '/dashboard/family', icon: Users },
    { name: t('notifications'), href: '/dashboard/notifications', icon: Bell },
    { name: t('settings'), href: '/dashboard/settings', icon: Settings },
  ];

  return (
    <aside className="hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:w-72 lg:flex-col">
      <div className="flex grow flex-col gap-y-5 overflow-y-auto border-r bg-card px-6 pb-4">
        <div className="flex h-16 shrink-0 items-center">
          <Link href="/dashboard" className="flex items-center gap-3">
            <img src="/logo.svg" alt={t('brandAlt')} className="h-8 w-8" />
            <span className="text-xl font-bold">{t('brandName')}</span>
          </Link>
        </div>
        <nav className="flex flex-1 flex-col">
          <ul role="list" className="flex flex-1 flex-col gap-y-7">
            <li>
              <ul role="list" className="-mx-2 space-y-1">
                {navigation.map((item) => {
                  // Dashboard only active on exact match, others match with prefix
                  const isActive = item.href === '/dashboard'
                    ? pathname === '/dashboard'
                    : pathname === item.href || pathname.startsWith(item.href + '/');
                  return (
                    <li key={item.name}>
                      <Link
                        href={item.href}
                        className={cn(
                          'group flex gap-x-3 rounded-md p-2 text-sm font-semibold leading-6',
                          isActive
                            ? 'bg-primary text-primary-foreground'
                            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                        )}
                      >
                        <item.icon className="h-6 w-6 shrink-0" aria-hidden="true" />
                        {item.name}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </li>
            <li>
              <div className="text-xs font-semibold leading-6 text-muted-foreground">
                {t('settingsLabel')}
              </div>
              <ul role="list" className="-mx-2 mt-2 space-y-1">
                {secondaryNavigation.map((item) => {
                  const matchesPath = pathname === item.href || pathname.startsWith(item.href + '/');
                  const claimedByPrimary = navigation.some(
                    (primary) => pathname === primary.href || pathname.startsWith(primary.href + '/')
                  );
                  const isActive = matchesPath && !claimedByPrimary;
                  return (
                    <li key={item.name}>
                      <Link
                        href={item.href}
                        className={cn(
                          'group flex gap-x-3 rounded-md p-2 text-sm font-semibold leading-6',
                          isActive
                            ? 'bg-primary text-primary-foreground'
                            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                        )}
                      >
                        <item.icon className="h-6 w-6 shrink-0" aria-hidden="true" />
                        {item.name}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </li>
          </ul>
        </nav>
      </div>
    </aside>
  );
}
