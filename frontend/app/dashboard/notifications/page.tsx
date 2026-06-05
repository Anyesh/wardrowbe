'use client';

import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import {
  Bell,
  Plus,
  Trash2,
  Send,
  Clock,
  Loader2,
  Settings2,
  Calendar,
  Mail,
  MessageSquare,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useNotificationSettings,
  useCreateNotificationSetting,
  useUpdateNotificationSetting,
  useDeleteNotificationSetting,
  useTestNotificationSetting,
  useSchedules,
  useCreateSchedule,
  useUpdateSchedule,
  useDeleteSchedule,
  NotificationSettings,
  Schedule,
} from '@/lib/hooks/use-notifications';
import { useUserProfile } from '@/lib/hooks/use-user';
import { useI18n } from '@/lib/i18n';
import { OCCASIONS } from '@/lib/types';

const DAY_VALUES = [0, 1, 2, 3, 4, 5, 6] as const;

const CHANNEL_ICONS: Record<string, React.ReactNode> = {
  ntfy: <Bell className="h-5 w-5" />,
  mattermost: <MessageSquare className="h-5 w-5" />,
  email: <Mail className="h-5 w-5" />,
};

function ChannelCard({
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
  const { t } = useI18n();

  const getChannelLabel = (channel: string) => {
    const labels: Record<string, string> = {
      ntfy: t('notifications.channelNtfy'),
      mattermost: t('notifications.channelMattermost'),
      email: t('notifications.channelEmail'),
    };
    return labels[channel] || channel;
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
              <p className="font-medium">{getChannelLabel(setting.channel)}</p>
              <p className="text-sm text-muted-foreground">
                {setting.channel === 'ntfy' && setting.config.topic}
                {setting.channel === 'mattermost' && t('notifications.webhookConfigured')}
                {setting.channel === 'email' && setting.config.address}
              </p>
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
            {t('notifications.test')}
          </Button>
          <Badge variant="secondary">
            {t('notifications.priority')} {setting.priority}
          </Badge>
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

interface ChannelFormData {
  channel: 'ntfy' | 'mattermost' | 'email';
  enabled: boolean;
  priority: number;
  config: Record<string, string>;
}

function AddChannelDialog({
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
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState<'ntfy' | 'mattermost' | 'email'>('ntfy');
  const [config, setConfig] = useState<Record<string, string>>({});
  const [ntfyDefaults, setNtfyDefaults] = useState<{ server: string; token: string } | null>(null);

  // Fetch ntfy defaults when dialog opens
  useEffect(() => {
    if (open && !ntfyDefaults) {
      fetch('/api/v1/notifications/defaults/ntfy')
        .then((res) => res.json())
        .then((data) => {
          setNtfyDefaults(data);
          if (channel === 'ntfy' && !config.server) {
            setConfig({ server: data.server, token: data.token || '' });
          }
        })
        .catch(() => {
          setNtfyDefaults({ server: 'https://ntfy.sh', token: '' });
        });
    }
  }, [open, ntfyDefaults, channel, config.server]);

  // Reset config when channel changes, pre-fill defaults per channel type
  useEffect(() => {
    if (channel === 'ntfy' && ntfyDefaults) {
      setConfig({ server: ntfyDefaults.server, token: ntfyDefaults.token });
    } else if (channel === 'email') {
      setConfig(userEmail ? { address: userEmail } : {});
    } else {
      setConfig({});
    }
  }, [channel, ntfyDefaults, userEmail]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Frontend validation
    if (channel === 'ntfy' && !config.topic?.trim()) {
      toast.error(t('notifications.ntfyTopicRequired'));
      return;
    }
    if (channel === 'mattermost' && !config.webhook_url?.trim()) {
      toast.error(t('notifications.mattermostWebhookRequired'));
      return;
    }
    if (channel === 'email' && !config.address?.trim()) {
      toast.error(t('notifications.emailRequired'));
      return;
    }

    try {
      await onAdd({
        channel,
        enabled: true,
        priority: 1,
        config,
      });
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
          {t('notifications.addChannel')}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t('notifications.addChannelTitle')}</DialogTitle>
            <DialogDescription>
              {t('notifications.addChannelDesc')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>{t('notifications.channelType')}</Label>
              <Select
                value={channel}
                onValueChange={(v: 'ntfy' | 'mattermost' | 'email') => {
                  setChannel(v);
                  setConfig({});
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ntfy">{t('notifications.channelNtfyFull')}</SelectItem>
                  <SelectItem value="mattermost">{t('notifications.channelMattermost')}</SelectItem>
                  <SelectItem value="email">{t('notifications.channelEmail')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {channel === 'ntfy' && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="server">{t('notifications.serverUrl')}</Label>
                  <Input
                    id="server"
                    value={config.server || 'https://ntfy.sh'}
                    onChange={(e) => setConfig({ ...config, server: e.target.value })}
                    placeholder="https://ntfy.sh"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="topic">{t('notifications.topicLabel')}</Label>
                  <Input
                    id="topic"
                    value={config.topic || ''}
                    onChange={(e) => setConfig({ ...config, topic: e.target.value })}
                    placeholder="my-wardrobe-notifications"
                    required
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('notifications.topicHint')}
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="token">{t('notifications.accessToken')}</Label>
                  <Input
                    id="token"
                    type="password"
                    value={config.token || ''}
                    onChange={(e) => setConfig({ ...config, token: e.target.value })}
                    placeholder="tk_..."
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('notifications.tokenHint')}
                  </p>
                </div>
              </>
            )}

            {channel === 'mattermost' && (
              <div className="space-y-2">
                <Label htmlFor="webhook">{t('notifications.webhookUrl')}</Label>
                <Input
                  id="webhook"
                  value={config.webhook_url || ''}
                  onChange={(e) => setConfig({ ...config, webhook_url: e.target.value })}
                  placeholder="https://mattermost.example.com/hooks/xxx"
                  required
                />
                <p className="text-xs text-muted-foreground">
                  {t('notifications.webhookHint')}
                </p>
              </div>
            )}

            {channel === 'email' && (
              <div className="space-y-2">
                <Label htmlFor="email">{t('notifications.emailAddress')}</Label>
                <Input
                  id="email"
                  type="email"
                  value={config.address || ''}
                  onChange={(e) => setConfig({ ...config, address: e.target.value })}
                  placeholder="you@example.com"
                  required
                />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeAndReset} disabled={isLoading}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  {t('notifications.adding')}
                </>
              ) : (
                t('notifications.addChannel')
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ScheduleCard({
  schedule,
  onToggle,
  onToggleDayBefore,
  onDelete,
}: {
  schedule: Schedule;
  onToggle: (enabled: boolean) => void;
  onToggleDayBefore: (notify_day_before: boolean) => void;
  onDelete: () => void;
}) {
  const { t } = useI18n();

  const getDayLabel = (dayValue: number) => {
    const labels: Record<number, string> = {
      0: t('dashboard.day.monday'),
      1: t('dashboard.day.tuesday'),
      2: t('dashboard.day.wednesday'),
      3: t('dashboard.day.thursday'),
      4: t('dashboard.day.friday'),
      5: t('dashboard.day.saturday'),
      6: t('dashboard.day.sunday'),
    };
    return labels[dayValue];
  };

  const getOccasionLabel = (val: string) => {
    const labels: Record<string, string> = {
      casual: t('notifications.occasion.casual'),
      office: t('notifications.occasion.office'),
      formal: t('notifications.occasion.formal'),
      date: t('notifications.occasion.date'),
      sporty: t('notifications.occasion.sporty'),
    };
    return labels[val] || OCCASIONS.find((o) => o.value === val)?.label || val;
  };

  const dayLabel = getDayLabel(schedule.day_of_week);
  const occasionLabel = getOccasionLabel(schedule.occasion);

  // Calculate which day the notification actually comes
  const notifyDayValue = schedule.notify_day_before
    ? (schedule.day_of_week + 6) % 7
    : schedule.day_of_week;
  const notifyDayLabel = getDayLabel(notifyDayValue);

  return (
    <div className="p-4 border rounded-lg space-y-3">
      {/* Top row: Day info and main toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-muted">
            <Calendar className="h-4 w-4" />
          </div>
          <div>
            <p className="font-medium">{dayLabel}</p>
            <p className="text-sm text-muted-foreground">
              {schedule.notification_time} - {occasionLabel}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Switch checked={schedule.enabled} onCheckedChange={onToggle} />
          <Button variant="ghost" size="sm" onClick={onDelete}>
            <Trash2 className="h-4 w-4 text-muted-foreground" />
          </Button>
        </div>
      </div>
      {/* Bottom row: Day before toggle */}
      <div className="flex items-center justify-between pt-2 border-t">
        <div className="flex items-center gap-2">
          <Switch
            id={`daybefore-${schedule.id}`}
            checked={schedule.notify_day_before}
            onCheckedChange={onToggleDayBefore}
          />
          <Label htmlFor={`daybefore-${schedule.id}`} className="text-sm cursor-pointer">
            {t('notifications.notifyDayBefore')}
          </Label>
        </div>
        {schedule.notify_day_before && (
          <span className="text-xs text-muted-foreground">
            {notifyDayLabel} {t('notifications.evening')}
          </span>
        )}
      </div>
    </div>
  );
}

interface ScheduleFormData {
  day_of_week: number;
  notification_time: string;
  occasion: string;
  enabled: boolean;
  notify_day_before: boolean;
}

function AddScheduleDialog({
  onAdd,
  isLoading,
}: {
  onAdd: (data: ScheduleFormData) => Promise<void>;
  isLoading: boolean;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [time, setTime] = useState('07:00');
  const [occasion, setOccasion] = useState('casual');
  const [notifyDayBefore, setNotifyDayBefore] = useState(false);
  const [dayOfWeek, setDayOfWeek] = useState<number>(0);

  const getDayLabel = (dayValue: number) => {
    const labels: Record<number, string> = {
      0: t('dashboard.day.monday'),
      1: t('dashboard.day.tuesday'),
      2: t('dashboard.day.wednesday'),
      3: t('dashboard.day.thursday'),
      4: t('dashboard.day.friday'),
      5: t('dashboard.day.saturday'),
      6: t('dashboard.day.sunday'),
    };
    return labels[dayValue];
  };

  const getOccasionLabel = (val: string) => {
    const labels: Record<string, string> = {
      casual: t('notifications.occasion.casual'),
      office: t('notifications.occasion.office'),
      formal: t('notifications.occasion.formal'),
      date: t('notifications.occasion.date'),
      sporty: t('notifications.occasion.sporty'),
    };
    return labels[val] || OCCASIONS.find((o) => o.value === val)?.label || val;
  };

  // Calculate which day notification comes on
  const notifyDayValue = notifyDayBefore
    ? (dayOfWeek + 6) % 7
    : dayOfWeek;
  const notifyDayLabel = getDayLabel(notifyDayValue);
  const targetDayLabel = getDayLabel(dayOfWeek);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await onAdd({
        day_of_week: dayOfWeek,
        notification_time: time,
        occasion,
        enabled: true,
        notify_day_before: notifyDayBefore,
      });
      setOpen(false);
      setTime('07:00');
      setOccasion('casual');
      setNotifyDayBefore(false);
    } catch {
      // Error handled by parent via toast
    }
  };

  const closeAndReset = () => {
    setOpen(false);
    setTime('07:00');
    setOccasion('casual');
    setNotifyDayBefore(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Plus className="h-4 w-4 mr-2" />
          {t('notifications.addSchedule')}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t('notifications.addScheduleTitle')}</DialogTitle>
            <DialogDescription>
              {t('notifications.addScheduleDesc')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>{t('notifications.day')}</Label>
              <Select
                value={String(dayOfWeek)}
                onValueChange={(v) => setDayOfWeek(parseInt(v))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DAY_VALUES.map((day) => (
                    <SelectItem key={day} value={String(day)}>
                      {getDayLabel(day)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="time">{t('notifications.time')}</Label>
              <Input
                id="time"
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>{t('notifications.occasion')}</Label>
              <Select value={occasion} onValueChange={setOccasion}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OCCASIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {getOccasionLabel(o.value)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/50">
              <div className="space-y-0.5">
                <Label htmlFor="notify-day-before">{t('notifications.notifyDayBefore')}</Label>
                <p className="text-xs text-muted-foreground">
                  {t('notifications.notifyDayBeforeDesc')}
                </p>
              </div>
              <Switch
                id="notify-day-before"
                checked={notifyDayBefore}
                onCheckedChange={setNotifyDayBefore}
              />
            </div>
            {notifyDayBefore && (
              <p className="text-sm text-muted-foreground bg-muted/30 p-2 rounded">
                {t('notifications.receiveNotifOn')} <strong>{notifyDayLabel}</strong> {t('notifications.atTime')} {time} {t('notifications.forYourOutfit')} <strong>{targetDayLabel}</strong> {t('notifications.outfitSuffix')}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeAndReset} disabled={isLoading}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  {t('notifications.adding')}
                </>
              ) : (
                t('notifications.addSchedule')
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function NotificationsPage() {
  const { t } = useI18n();
  const { data: settings, isLoading: loadingSettings } = useNotificationSettings();
  const { data: schedules, isLoading: loadingSchedules } = useSchedules();
  const { data: userProfile } = useUserProfile();

  const createSetting = useCreateNotificationSetting();
  const updateSetting = useUpdateNotificationSetting();
  const deleteSetting = useDeleteNotificationSetting();
  const testSetting = useTestNotificationSetting();

  const createSchedule = useCreateSchedule();
  const updateSchedule = useUpdateSchedule();
  const deleteSchedule = useDeleteSchedule();

  const [testingId, setTestingId] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ type: 'channel' | 'schedule'; id: string } | null>(null);

  const handleCreateChannel = async (data: ChannelFormData): Promise<void> => {
    try {
      await createSetting.mutateAsync(data);
      toast.success(t('notifications.channelAdded'));
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('notifications.channelAddError');
      toast.error(message);
      throw error;
    }
  };

  const handleCreateSchedule = async (data: ScheduleFormData): Promise<void> => {
    try {
      await createSchedule.mutateAsync(data);
      toast.success(t('notifications.scheduleAdded'));
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('notifications.scheduleAddError');
      toast.error(message);
      throw error;
    }
  };

  const handleTest = async (id: string) => {
    setTestingId(id);
    try {
      const result = await testSetting.mutateAsync(id);
      toast.success(result.message || t('notifications.testSuccess'));
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('notifications.testFailed');
      toast.error(message);
    } finally {
      setTestingId(null);
    }
  };

  const handleToggleChannel = async (id: string, enabled: boolean) => {
    try {
      await updateSetting.mutateAsync({ id, data: { enabled } });
      toast.success(enabled ? t('notifications.channelEnabled') : t('notifications.channelDisabled'));
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('notifications.updateFailed');
      toast.error(message);
    }
  };

  const handleToggleSchedule = async (id: string, enabled: boolean) => {
    try {
      await updateSchedule.mutateAsync({ id, data: { enabled } });
      toast.success(enabled ? t('notifications.scheduleEnabled') : t('notifications.scheduleDisabled'));
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('notifications.updateFailed');
      toast.error(message);
    }
  };

  const handleToggleDayBefore = async (id: string, notify_day_before: boolean) => {
    try {
      await updateSchedule.mutateAsync({ id, data: { notify_day_before } });
      toast.success(notify_day_before ? t('notifications.willNotifyDayBefore') : t('notifications.willNotifySameDay'));
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('notifications.updateFailed');
      toast.error(message);
    }
  };

  const handleDeleteConfirmed = async () => {
    if (!deleteConfirm) return;

    try {
      if (deleteConfirm.type === 'channel') {
        await deleteSetting.mutateAsync(deleteConfirm.id);
        toast.success(t('notifications.channelDeleted'));
      } else {
        await deleteSchedule.mutateAsync(deleteConfirm.id);
        toast.success(t('notifications.scheduleDeleted'));
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('notifications.deleteFailed');
      toast.error(message);
    } finally {
      setDeleteConfirm(null);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t('notifications.title')}</h1>
        <p className="text-muted-foreground">
          {t('notifications.subtitle')}
        </p>
      </div>

      {/* Notification Channels */}
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Settings2 className="h-5 w-5" />
                {t('notifications.channelSection')}
              </CardTitle>
              <CardDescription>
                {t('notifications.channelSectionDesc')}
              </CardDescription>
            </div>
            <AddChannelDialog onAdd={handleCreateChannel} isLoading={createSetting.isPending} userEmail={userProfile?.email} />
          </div>
        </CardHeader>
        <CardContent>
          {loadingSettings ? (
            <div className="space-y-4">
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
            </div>
          ) : settings?.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Bell className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>{t('notifications.noChannels')}</p>
              <p className="text-sm">{t('notifications.noChannelsHint')}</p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {settings?.map((setting) => (
                <ChannelCard
                  key={setting.id}
                  setting={setting}
                  testing={testingId === setting.id}
                  onTest={() => handleTest(setting.id)}
                  onToggle={(enabled) => handleToggleChannel(setting.id, enabled)}
                  onDelete={() => setDeleteConfirm({ type: 'channel', id: setting.id })}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Schedules */}
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                {t('notifications.scheduleSection')}
              </CardTitle>
              <CardDescription>
                {t('notifications.scheduleSectionDesc')}
              </CardDescription>
            </div>
            <AddScheduleDialog
              onAdd={handleCreateSchedule}
              isLoading={createSchedule.isPending}
            />
          </div>
        </CardHeader>
        <CardContent>
          {loadingSchedules ? (
            <div className="space-y-4">
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
            </div>
          ) : schedules?.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Calendar className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>{t('notifications.noSchedules')}</p>
              <p className="text-sm">{t('notifications.noSchedulesHint')}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {DAY_VALUES.map((dayVal) => {
                const daySchedules = schedules?.filter((s) => s.day_of_week === dayVal) || [];
                if (daySchedules.length === 0) return null;
                return daySchedules.map((schedule) => (
                  <ScheduleCard
                    key={schedule.id}
                    schedule={schedule}
                    onToggle={(enabled) => handleToggleSchedule(schedule.id, enabled)}
                    onToggleDayBefore={(notify_day_before) => handleToggleDayBefore(schedule.id, notify_day_before)}
                    onDelete={() => setDeleteConfirm({ type: 'schedule', id: schedule.id })}
                  />
                ));
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteConfirm} onOpenChange={(open) => !open && setDeleteConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {deleteConfirm?.type === 'channel'
                ? t('notifications.deleteChannelTitle')
                : t('notifications.deleteScheduleTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {deleteConfirm?.type === 'channel'
                ? t('notifications.deleteChannelDesc')
                : t('notifications.deleteScheduleDesc')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirmed}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteSetting.isPending || deleteSchedule.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  {t('notifications.deleting')}
                </>
              ) : (
                t('common.delete')
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}