'use client';

import { useState } from 'react';
import { useSession } from 'next-auth/react';
import { useI18n } from '@/lib/i18n';
import { toast } from 'sonner';
import {
  Loader2,
  Users,
  Copy,
  Check,
  RefreshCw,
  UserPlus,
  LogOut,
  Crown,
  Trash2,
  Mail,
  Clock,
  Shield,
  Star,
  Shirt,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  useFamily,
  useCreateFamily,
  useJoinFamily,
  useLeaveFamily,
  useRegenerateInviteCode,
  useInviteMember,
  useCancelInvite,
  useUpdateMemberRole,
  useRemoveMember,
  useUpdateFamily,
} from '@/lib/hooks/use-family';
import Link from 'next/link';

function NoFamilyView() {
  const { t } = useI18n();
  const [mode, setMode] = useState<'create' | 'join' | null>(null);
  const [familyName, setFamilyName] = useState('');
  const [inviteCode, setInviteCode] = useState('');

  const createFamily = useCreateFamily();
  const joinFamily = useJoinFamily();

  const handleCreate = async () => {
    if (!familyName.trim()) return;
    try {
      await createFamily.mutateAsync(familyName.trim());
      toast.success(t('family.createSuccess'));
      setFamilyName('');
      setMode(null);
    } catch (error) {
      toast.error(t('family.createError'));
    }
  };

  const handleJoin = async () => {
    if (!inviteCode.trim()) return;
    try {
      await joinFamily.mutateAsync(inviteCode.trim().toUpperCase());
      toast.success(t('family.joinSuccess'));
      setInviteCode('');
      setMode(null);
    } catch (error) {
      toast.error(t('family.invalidCode'));
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t('family.title')}</h1>
        <p className="text-muted-foreground">
          {t('family.subtitle')}
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2 max-w-2xl">
        <Card className={mode === 'create' ? 'ring-2 ring-primary' : ''}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              {t('family.create')}
            </CardTitle>
            <CardDescription>{t('family.createDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            {mode === 'create' ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="family-name">{t('family.familyName')}</Label>
                  <Input
                    id="family-name"
                    placeholder="e.g., The Smith Family"
                    value={familyName}
                    onChange={(e) => setFamilyName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={handleCreate}
                    disabled={!familyName.trim() || createFamily.isPending}
                  >
                    {createFamily.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {t('family.create')}
                  </Button>
                  <Button variant="outline" onClick={() => setMode(null)}>
                    {t('common.cancel')}
                  </Button>
                </div>
              </div>
            ) : (
              <Button onClick={() => setMode('create')} className="w-full">
                {t('family.create')}
              </Button>
            )}
          </CardContent>
        </Card>

        <Card className={mode === 'join' ? 'ring-2 ring-primary' : ''}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserPlus className="h-5 w-5" />
              {t('family.join')}
            </CardTitle>
            <CardDescription>{t('family.joinDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            {mode === 'join' ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="invite-code">{t('family.inviteCode')}</Label>
                  <Input
                    id="invite-code"
                    placeholder="e.g., ABC123XY"
                    value={inviteCode}
                    onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                    onKeyDown={(e) => e.key === 'Enter' && handleJoin()}
                    className="font-mono uppercase"
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={handleJoin}
                    disabled={!inviteCode.trim() || joinFamily.isPending}
                  >
                    {joinFamily.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {t('family.join')}
                  </Button>
                  <Button variant="outline" onClick={() => setMode(null)}>
                    {t('common.cancel')}
                  </Button>
                </div>
                {joinFamily.isError && (
                  <p className="text-sm text-destructive">
                    {t('family.invalidCode')}
                  </p>
                )}
              </div>
            ) : (
              <Button onClick={() => setMode('join')} variant="outline" className="w-full">
                {t('family.join')}
              </Button>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function FamilyView() {
  const { t } = useI18n();
  const { data: session } = useSession();
  const { data: family, isLoading } = useFamily();
  const [copied, setCopied] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'member' | 'admin'>('member');
  const [editingName, setEditingName] = useState(false);
  const [newName, setNewName] = useState('');

  const leaveFamily = useLeaveFamily();
  const regenerateCode = useRegenerateInviteCode();
  const inviteMember = useInviteMember();
  const cancelInvite = useCancelInvite();
  const updateRole = useUpdateMemberRole();
  const removeMember = useRemoveMember();
  const updateFamily = useUpdateFamily();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!family) {
    return <NoFamilyView />;
  }

  // Match by email since session user id (external_id) differs from member id (UUID)
  const currentEmail = session?.user?.email;
  const currentMember = family.members.find((m) => m.email === currentEmail);
  const isAdmin = currentMember?.role === 'admin';

  const copyInviteCode = () => {
    navigator.clipboard.writeText(family.invite_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRegenerateCode = async () => {
    try {
      await regenerateCode.mutateAsync();
      toast.success(t('family.codeRegenerated'));
    } catch (error) {
      toast.error(t('family.codeRegenerateError'));
    }
  };

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    try {
      await inviteMember.mutateAsync({ email: inviteEmail.trim(), role: inviteRole });
      toast.success(t('family.inviteSent'));
      setInviteEmail('');
    } catch (error) {
      toast.error(t('family.inviteFailed'));
    }
  };

  const handleUpdateName = async () => {
    if (!newName.trim()) return;
    try {
      await updateFamily.mutateAsync(newName.trim());
      toast.success(t('family.nameUpdated'));
      setEditingName(false);
      setNewName('');
    } catch (error) {
      toast.error(t('family.nameUpdateError'));
    }
  };

  const getInitials = (name: string) => {
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{family.name}</h1>
          <p className="text-muted-foreground">
            {family.members.length}{' '}
            {family.members.length === 1 ? t('family.member') : t('family.members')}
          </p>
        </div>
        <div className="flex gap-2">
          {isAdmin && (
            <Button
              variant="outline"
              onClick={() => {
                setNewName(family.name);
                setEditingName(true);
              }}
            >
              {t('family.editName')}
            </Button>
          )}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive">
                <LogOut className="mr-2 h-4 w-4" />
                {t('family.leaveFamily')}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t('family.leaveTitle')}</AlertDialogTitle>
                <AlertDialogDescription>
                  {isAdmin && family.members.length > 1
                    ? t('family.leaveAdminWarning')
                    : t('family.leaveConfirm')}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => leaveFamily.mutate()}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {leaveFamily.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  {t('family.leave')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {/* Edit Name Dialog */}
      {editingName && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex gap-2">
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder={t('family.namePlaceholder')}
                onKeyDown={(e) => e.key === 'Enter' && handleUpdateName()}
              />
              <Button onClick={handleUpdateName} disabled={updateFamily.isPending}>
                {updateFamily.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('common.save')}
              </Button>
              <Button variant="outline" onClick={() => setEditingName(false)}>
                {t('common.cancel')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Invite Code Card */}
      <Card>
        <CardHeader>
          <CardTitle>{t('family.inviteCode')}</CardTitle>
          <CardDescription>{t('family.inviteCodeDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <code className="flex-1 rounded-md bg-muted px-4 py-3 font-mono text-lg tracking-wider">
              {family.invite_code}
            </code>
            <Button variant="outline" size="icon" onClick={copyInviteCode}>
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </Button>
            {isAdmin && (
              <Button
                variant="outline"
                size="icon"
                onClick={handleRegenerateCode}
                disabled={regenerateCode.isPending}
              >
                {regenerateCode.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Send Email Invite (Admin only) */}
      {isAdmin && (
        <Card>
          <CardHeader>
            <CardTitle>{t('family.sendInvite')}</CardTitle>
            <CardDescription>{t('family.inviteByEmail')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Input
                type="email"
                placeholder="email@example.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleInvite()}
              />
              <Select
                value={inviteRole}
                onValueChange={(v) => setInviteRole(v as 'member' | 'admin')}
              >
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="member">{t('family.member')}</SelectItem>
                  <SelectItem value="admin">{t('family.admin')}</SelectItem>
                </SelectContent>
              </Select>
              <Button onClick={handleInvite} disabled={!inviteEmail.trim() || inviteMember.isPending}>
                {inviteMember.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                <Mail className="mr-2 h-4 w-4" />
                {t('family.invite')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Members List */}
      <Card>
        <CardHeader>
          <CardTitle>{t('family.members')}</CardTitle>
          <CardDescription>{t('family.membersDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {family.members.map((member) => (
              <div
                key={member.id}
                className="flex items-center justify-between p-4 rounded-lg border"
              >
                <div className="flex items-center gap-3">
                  <Avatar>
                    <AvatarImage src={member.avatar_url} />
                    <AvatarFallback>{getInitials(member.display_name)}</AvatarFallback>
                  </Avatar>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{member.display_name}</span>
                      {member.email === currentEmail && (
                        <Badge variant="secondary" className="text-xs">
                          {t('family.you')}
                        </Badge>
                      )}
                      {member.role === 'admin' && (
                        <Badge variant="outline" className="text-xs gap-1">
                          <Crown className="h-3 w-3" />
                          {t('family.admin')}
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground">{member.email}</p>
                  </div>
                </div>
                {isAdmin && member.email !== currentEmail && (
                  <div className="flex items-center gap-2">
                    <Select
                      value={member.role}
                      onValueChange={(role) =>
                        updateRole.mutate({ memberId: member.id, role })
                      }
                    >
                      <SelectTrigger className="w-28">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="member">{t('family.member')}</SelectItem>
                        <SelectItem value="admin">{t('family.admin')}</SelectItem>
                      </SelectContent>
                    </Select>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="ghost" size="icon" className="text-destructive">
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>{t('family.removeMemberTitle')}</AlertDialogTitle>
                          <AlertDialogDescription>
                            {t('family.remove')} {member.display_name} {t('family.removeMemberDesc')}
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => removeMember.mutate(member.id)}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          >
                            {t('family.remove')}
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Pending Invites */}
      {isAdmin && family.pending_invites.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t('family.pendingInvites')}</CardTitle>
            <CardDescription>{t('family.pendingInvitesDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {family.pending_invites.map((invite) => (
                <div
                  key={invite.id}
                  className="flex items-center justify-between p-4 rounded-lg border"
                >
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
                      <Mail className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div>
                      <span className="font-medium">{invite.email}</span>
                      <div className="flex items-center gap-1 text-sm text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {t('family.expires')} {new Date(invite.expires_at).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-destructive"
                    onClick={() => cancelInvite.mutate(invite.id)}
                    disabled={cancelInvite.isPending}
                  >
                    {cancelInvite.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Family Outfits Feed */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shirt className="h-5 w-5" />
            {t('family.familyOutfits')}
          </CardTitle>
          <CardDescription>{t('family.familyOutfitsDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild className="w-full">
            <Link href="/dashboard/family/feed">
              <Star className="mr-2 h-4 w-4" />
              {t('family.openFeed')}
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default function FamilyPage() {
  const { data: family, isLoading, isError } = useFamily();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // If error (404 - no family) or no data, show create/join view
  if (isError || !family) {
    return <NoFamilyView />;
  }

  return <FamilyView />;
}