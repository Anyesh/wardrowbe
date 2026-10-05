'use client';

import type { ReactNode } from 'react';
import { Bell, Loader2, Mail, MessageSquare, Send, Smartphone, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import type { NotificationChannel, NotificationSettings } from '@/lib/hooks/use-notifications';

const CHANNEL_ICONS: Record<NotificationChannel, ReactNode> = {
  ntfy: <Bell className="h-5 w-5" />,
  mattermost: <MessageSquare className="h-5 w-5" />,
  email: <Mail className="h-5 w-5" />,
  expo_push: <Smartphone className="h-5 w-5" />,
};

export function ChannelCard({
  setting,
  onTest,
  onToggle,
  onDelete,
  testing,
}: {
  setting: NotificationSettings;
  onTest: () => void;
  onToggle: (enabled: boolean) => void;
  onDelete: () => void;
  testing: boolean;
}) {
  const t = useTranslations('notifications');
  const details: Record<NotificationChannel, ReactNode> = {
    ntfy: setting.config.topic,
    mattermost: t('channels.webhookConfigured'),
    email: setting.config.address,
    expo_push: t('channels.mobileAppRegistered'),
  };
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              {CHANNEL_ICONS[setting.channel]}
            </div>
            <div>
              <p className="font-medium">{t(`channels.types.${setting.channel}`)}</p>
              <p className="text-sm text-muted-foreground">{details[setting.channel]}</p>
            </div>
          </div>
          <Switch checked={setting.enabled} onCheckedChange={onToggle} />
        </div>
        <div className="flex items-center gap-2 mt-4">
          <Button
            variant="outline"
            size="sm"
            onClick={onTest}
            disabled={testing || !setting.enabled}
          >
            {testing ? (
              <Loader2 className="h-4 w-4 animate-spin mr-1" />
            ) : (
              <Send className="h-4 w-4 mr-1" />
            )}
            {t('channels.test')}
          </Button>
          <Badge variant="secondary">{t('channels.priority', { level: setting.priority })}</Badge>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto text-destructive hover:text-destructive"
            onClick={onDelete}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
