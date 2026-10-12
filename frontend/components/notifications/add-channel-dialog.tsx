'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Loader2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { ManualNotificationChannel, useNtfyDefaults } from '@/lib/hooks/use-notifications';
import { isDeliverableEmail } from '@/lib/utils';

// Kept out of the catalogs because an ntfy topic is part of a URL and reads the same in every locale.
const EXAMPLE_NTFY_TOPIC = 'my-wardrobe-notifications';

const normalizeServer = (url: string) => url.trim().replace(/\/+$/, '');

export interface ChannelFormData {
  channel: ManualNotificationChannel;
  enabled: boolean;
  priority: number;
  config: Record<string, string>;
}

export function AddChannelDialog({
  onAdd,
  isLoading,
  onSuccess,
  userEmail,
}: {
  onAdd: (data: ChannelFormData) => Promise<void>;
  isLoading: boolean;
  onSuccess?: () => void;
  userEmail?: string;
}) {
  const t = useTranslations('notifications');
  const tc = useTranslations('common');
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState<ManualNotificationChannel>('ntfy');
  const [config, setConfig] = useState<Record<string, string>>({});
  const { data: ntfyDefaults } = useNtfyDefaults(open);

  // Reset config when channel changes, pre-fill defaults per channel type
  useEffect(() => {
    if (channel === 'ntfy' && ntfyDefaults) {
      setConfig((prev) => (prev.server ? prev : { ...prev, server: ntfyDefaults.server }));
    } else if (channel === 'email') {
      setConfig(isDeliverableEmail(userEmail) ? { address: userEmail } : {});
    } else {
      setConfig({});
    }
  }, [channel, ntfyDefaults, userEmail]);

  const usesServerToken =
    !!ntfyDefaults?.has_token &&
    !config.token &&
    normalizeServer(config.server ?? '') === normalizeServer(ntfyDefaults.server);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Frontend validation
    if (channel === 'ntfy' && !config.topic?.trim()) {
      toast.error(t('channels.validation.topicRequired'));
      return;
    }
    if (channel === 'mattermost' && !config.webhook_url?.trim()) {
      toast.error(t('channels.validation.webhookRequired'));
      return;
    }
    if (channel === 'email' && !config.address?.trim()) {
      toast.error(t('channels.validation.emailRequired'));
      return;
    }

    try {
      await onAdd({
        channel,
        enabled: true,
        priority: 1,
        config,
      });
      // Close and reset on success
      setOpen(false);
      setConfig({});
      setChannel('ntfy');
      onSuccess?.();
    } catch {
      // Error handled by parent via toast
    }
  };

  const closeAndReset = () => {
    setOpen(false);
    setConfig({});
    setChannel('ntfy');
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4 mr-2" />
          {t('channels.addChannel')}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t('channels.dialog.title')}</DialogTitle>
            <DialogDescription>
              {t('channels.dialog.description')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>{t('channels.channelType')}</Label>
              <Select
                value={channel}
                onValueChange={(v: ManualNotificationChannel) => {
                  setChannel(v);
                  setConfig({});
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ntfy">{t('channels.types.ntfy')}</SelectItem>
                  <SelectItem value="mattermost">{t('channels.types.mattermost')}</SelectItem>
                  <SelectItem value="email">{t('channels.types.email')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {channel === 'ntfy' && (
              <>
                <div className="space-y-2">
                  <Label>{t('channels.fields.serverUrl')}</Label>
                  <Input
                    id="server"
                    value={config.server || 'https://ntfy.sh'}
                    onChange={(e) => setConfig({ ...config, server: e.target.value })}
                    placeholder="https://ntfy.sh"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="topic">{t('channels.fields.topic')}</Label>
                  <Input
                    id="topic"
                    value={config.topic || ''}
                    onChange={(e) => setConfig({ ...config, topic: e.target.value })}
                    placeholder={EXAMPLE_NTFY_TOPIC}
                    required
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('channels.helpers.topicSubscribe')}
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="token">{t('channels.fields.accessToken')}</Label>
                  <Input
                    id="token"
                    type="password"
                    value={config.token || ''}
                    onChange={(e) => setConfig({ ...config, token: e.target.value })}
                    placeholder={t('channels.placeholders.accessToken')}
                  />
                  <p className="text-xs text-muted-foreground">
                    {usesServerToken
                      ? t('channels.helpers.accessTokenServerDefault')
                      : t('channels.helpers.accessTokenOptional')}
                  </p>
                </div>
              </>
            )}

            {channel === 'mattermost' && (
              <div className="space-y-2">
                <Label htmlFor="webhook">{t('channels.fields.webhookUrl')}</Label>
                <Input
                  id="webhook"
                  value={config.webhook_url || ''}
                  onChange={(e) => setConfig({ ...config, webhook_url: e.target.value })}
                  placeholder="https://mattermost.example.com/hooks/xxx"
                  required
                />
                <p className="text-xs text-muted-foreground">
                  {t('channels.helpers.mattermostWebhook')}
                </p>
              </div>
            )}

            {channel === 'email' && (
              <div className="space-y-2">
                <Label htmlFor="email">{t('channels.fields.emailAddress')}</Label>
                <Input
                  id="email"
                  type="email"
                  value={config.address || ''}
                  onChange={(e) => setConfig({ ...config, address: e.target.value })}
                  placeholder={t('channels.placeholders.emailAddress')}
                  required
                />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeAndReset} disabled={isLoading}>
              {tc('cancel')}
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  {tc('adding')}
                </>
              ) : (
                t('channels.addChannel')
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
