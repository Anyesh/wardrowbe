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

const navigation = [
  { name: '概览', href: '/dashboard', icon: Home },
  { name: '衣橱', href: '/dashboard/wardrobe', icon: Shirt },
  { name: '穿搭建议', href: '/dashboard/suggest', icon: Sparkles },
  { name: '穿搭', href: '/dashboard/outfits', icon: LayoutGrid },
  { name: '搭配', href: '/dashboard/pairings', icon: Layers },
  { name: '历史', href: '/dashboard/history', icon: History },
  { name: '家庭动态', href: '/dashboard/family/feed', icon: HeartHandshake },
  { name: '分析', href: '/dashboard/analytics', icon: BarChart3 },
  { name: 'AI 学习', href: '/dashboard/learning', icon: Brain },
];

const secondaryNavigation = [
  { name: '家庭', href: '/dashboard/family', icon: Users },
  { name: '通知', href: '/dashboard/notifications', icon: Bell },
  { name: '设置', href: '/dashboard/settings', icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:w-72 lg:flex-col">
      <div className="flex grow flex-col gap-y-5 overflow-y-auto border-r bg-card px-6 pb-4">
        <div className="flex h-16 shrink-0 items-center">
          <Link href="/dashboard" className="flex items-center gap-3">
            <img src="/logo.svg" alt="Wardrowbe" className="h-8 w-8" />
            <span className="text-xl font-bold">wardrowbe</span>
          </Link>
        </div>
        <nav className="flex flex-1 flex-col">
          <ul role="list" className="flex flex-1 flex-col gap-y-7">
            <li>
              <ul role="list" className="-mx-2 space-y-1">
                {navigation.map((item) => {
                  // 概览 only active on exact match, others match with prefix
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
                设置
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
