'use client';

import { Menu, Moon, Sun, LogOut, Languages } from 'lucide-react';
import { useTheme } from 'next-themes';
import { signOut } from 'next-auth/react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/hooks/use-auth';
import { useI18n } from '@/lib/i18n';

interface HeaderProps {
  onMenuClick?: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const { lang, setLang, t } = useI18n();

  const toggleTheme = () => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  };

  const handleLogout = () => {
    signOut({ callbackUrl: '/login' });
  };

  const getInitials = (name?: string | null) => {
    if (!name) return '?';
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  return (
    <header className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-x-4 border-b bg-background px-4 shadow-sm sm:gap-x-6 sm:px-6 lg:px-8">
      <button
        type="button"
        className="-m-2.5 p-2.5 text-muted-foreground lg:hidden"
        onClick={onMenuClick}
      >
        <span className="sr-only">{t('header.openSidebar')}</span>
        <Menu className="h-6 w-6" aria-hidden="true" />
      </button>

      <div className="h-6 w-px bg-border lg:hidden" aria-hidden="true" />

      <div className="flex flex-1 gap-x-4 self-stretch lg:gap-x-6">
        <div className="flex flex-1" />
        <div className="flex items-center gap-x-4 lg:gap-x-6">
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            aria-label={t('header.toggleTheme')}
          >
            <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          </Button>

          <div className="relative group">
            <Button
              variant="ghost"
              size="icon"
              aria-label={t('header.toggleLang')}
            >
              <Languages className="h-5 w-5" />
            </Button>
            <div className="absolute right-0 top-full hidden group-hover:flex flex-col bg-popover border rounded-md shadow-md z-50 min-w-[80px] overflow-hidden">
              <button
                className={`px-3 py-2 text-sm hover:bg-accent text-left ${lang === 'zh' ? 'font-bold bg-accent/50' : ''}`}
                onClick={() => setLang('zh')}
              >
                中文
              </button>
              <button
                className={`px-3 py-2 text-sm hover:bg-accent text-left ${lang === 'en' ? 'font-bold bg-accent/50' : ''}`}
                onClick={() => setLang('en')}
              >
                English
              </button>
            </div>
          </div>

          <div className="hidden lg:block lg:h-6 lg:w-px lg:bg-border" aria-hidden="true" />

          <div className="flex items-center gap-x-4">
            <Avatar className="h-8 w-8">
              <AvatarImage src={user?.avatar_url || ''} alt={user?.display_name || ''} />
              <AvatarFallback>{getInitials(user?.display_name)}</AvatarFallback>
            </Avatar>
            <span className="hidden text-sm font-semibold lg:block">
              {user?.display_name || 'User'}
            </span>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleLogout}
              aria-label={t('header.signOut')}
            >
              <LogOut className="h-5 w-5" />
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}
