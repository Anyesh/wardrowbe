'use client';

import { useState } from 'react';
import { useSession } from 'next-auth/react';
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
  const [mode, setMode] = useState<'create' | 'join' | null>(null);
  const [familyName, setFamilyName] = useState('');
  const [inviteCode, setInviteCode] = useState('');

  const createFamily = useCreateFamily();
  const joinFamily = useJoinFamily();

  const handleCreate = async () => {
    if (!familyName.trim()) return;
    try {
      await createFamily.mutateAsync(familyName.trim());
      toast.success('家庭已创建！');
      setFamilyName('');
      setMode(null);
    } catch (error) {
      toast.error('创建家庭失败，请重试。');
    }
  };

  const handleJoin = async () => {
    if (!inviteCode.trim()) return;
    try {
      await joinFamily.mutateAsync(inviteCode.trim().toUpperCase());
      toast.success('已加入家庭！');
      setInviteCode('');
      setMode(null);
    } catch (error) {
      toast.error('邀请码无效，请检查后重试。');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">家庭</h1>
        <p className="text-muted-foreground">
          创建或加入家庭，一起分享衣橱体验
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2 max-w-2xl">
        <Card className={mode === 'create' ? 'ring-2 ring-primary' : ''}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              创建家庭
            </CardTitle>
            <CardDescription>创建一个新的家庭并邀请成员加入</CardDescription>
          </CardHeader>
          <CardContent>
            {mode === 'create' ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="family-name">家庭名称</Label>
                  <Input
                    id="family-name"
                    placeholder="例如：张家衣橱"
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
                    Create
                  </Button>
                  <Button variant="outline" onClick={() => setMode(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Button onClick={() => setMode('create')} className="w-full">
                创建家庭
              </Button>
            )}
          </CardContent>
        </Card>

        <Card className={mode === 'join' ? 'ring-2 ring-primary' : ''}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserPlus className="h-5 w-5" />
              加入家庭
            </CardTitle>
            <CardDescription>通过邀请码加入一个已有家庭</CardDescription>
          </CardHeader>
          <CardContent>
            {mode === 'join' ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="invite-code">邀请码</Label>
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
                    Join
                  </Button>
                  <Button variant="outline" onClick={() => setMode(null)}>
                    Cancel
                  </Button>
                </div>
                {joinFamily.isError && (
                  <p className="text-sm text-destructive">
                    邀请码无效，请检查后重试。
                  </p>
                )}
              </div>
            ) : (
              <Button onClick={() => setMode('join')} variant="outline" className="w-full">
                加入家庭
              </Button>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function FamilyView() {
  const { data: session } = useSession();
  const { data: family, isLoading } = useFamily();
  const [copied, setCopied] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [invite角色, setInvite角色] = useState<'member' | 'admin'>('member');
  const [editingName, setEditingName] = useState(false);
  const [newName, setNewName] = useState('');

  const leaveFamily = useLeaveFamily();
  const regenerateCode = useRegenerateInviteCode();
  const invite成员 = useInviteMember();
  const cancelInvite = useCancelInvite();
  const update角色 = useUpdateMemberRole();
  const remove成员 = useRemoveMember();
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
  const current成员 = family.members.find((m) => m.email === currentEmail);
  const is管理员 = current成员?.role === 'admin';

  const copyInviteCode = () => {
    navigator.clipboard.writeText(family.invite_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handle重新生成Code = async () => {
    try {
      await regenerateCode.mutateAsync();
      toast.success('已生成新的邀请码！');
    } catch (error) {
      toast.error('Failed to generate new code. Please try again.');
    }
  };

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    try {
      await invite成员.mutateAsync({ email: inviteEmail.trim(), role: invite角色 });
      toast.success('邀请已发送！');
      setInviteEmail('');
    } catch (error) {
      toast.error('Failed to send invite. Please try again.');
    }
  };

  const handleUpdateName = async () => {
    if (!newName.trim()) return;
    try {
      await updateFamily.mutateAsync(newName.trim());
      toast.success('家庭名称已更新！');
      setEditingName(false);
      setNewName('');
    } catch (error) {
      toast.error('更新名称失败，请重试。');
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
            {family.members.length} member{family.members.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-2">
          {is管理员 && (
            <Button
              variant="outline"
              onClick={() => {
                setNewName(family.name);
                setEditingName(true);
              }}
            >
              Edit Name
            </Button>
          )}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive">
                <LogOut className="mr-2 h-4 w-4" />
                Leave Family
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>确认退出家庭？</AlertDialogTitle>
                <AlertDialogDescription>
                  {is管理员 && family.members.length > 1
                    ? '你当前是管理员。退出前请先确保有其他管理员，或者先移除其他成员。'
                    : '确定要退出这个家庭吗？'}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>取消</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => leaveFamily.mutate()}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {leaveFamily.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  Leave
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
                placeholder="家庭名称"
                onKeyDown={(e) => e.key === 'Enter' && handleUpdateName()}
              />
              <Button onClick={handleUpdateName} disabled={updateFamily.isPending}>
                {updateFamily.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save
              </Button>
              <Button variant="outline" onClick={() => setEditingName(false)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 邀请码 Card */}
      <Card>
        <CardHeader>
          <CardTitle>邀请码</CardTitle>
          <CardDescription>把这个邀请码发给家庭成员，他们就能加入。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <code className="flex-1 rounded-md bg-muted px-4 py-3 font-mono text-lg tracking-wider">
              {family.invite_code}
            </code>
            <Button variant="outline" size="icon" onClick={copyInviteCode}>
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </Button>
            {is管理员 && (
              <Button
                variant="outline"
                size="icon"
                onClick={handle重新生成Code}
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

      {/* Send Email Invite (管理员 only) */}
      {is管理员 && (
        <Card>
          <CardHeader>
            <CardTitle>发送邀请</CardTitle>
            <CardDescription>Invite someone by email</CardDescription>
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
                value={invite角色}
                onValueChange={(v) => setInvite角色(v as 'member' | 'admin')}
              >
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="member">成员</SelectItem>
                  <SelectItem value="admin">管理员</SelectItem>
                </SelectContent>
              </Select>
              <Button onClick={handleInvite} disabled={!inviteEmail.trim() || invite成员.isPending}>
                {invite成员.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                <Mail className="mr-2 h-4 w-4" />
                Invite
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 成员s List */}
      <Card>
        <CardHeader>
          <CardTitle>成员s</CardTitle>
          <CardDescription>People in your family</CardDescription>
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
                          You
                        </Badge>
                      )}
                      {member.role === 'admin' && (
                        <Badge variant="outline" className="text-xs gap-1">
                          <Crown className="h-3 w-3" />
                          管理员
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground">{member.email}</p>
                  </div>
                </div>
                {is管理员 && member.email !== currentEmail && (
                  <div className="flex items-center gap-2">
                    <Select
                      value={member.role}
                      onValueChange={(role) =>
                        update角色.mutate({ memberId: member.id, role })
                      }
                    >
                      <SelectTrigger className="w-28">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="member">成员</SelectItem>
                        <SelectItem value="admin">管理员</SelectItem>
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
                          <AlertDialogTitle>Remove 成员?</AlertDialogTitle>
                          <AlertDialogDescription>
                            Remove {member.display_name} from the family?
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>取消</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => remove成员.mutate(member.id)}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          >
                            Remove
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

      {/* 待处理邀请 */}
      {is管理员 && family.pending_invites.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>待处理邀请</CardTitle>
            <CardDescription>Invitations that haven&apos;t been accepted yet</CardDescription>
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
                        Expires {new Date(invite.expires_at).toLocaleDateString()}
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
            Family Outfits
          </CardTitle>
          <CardDescription>查看并评价家庭成员的穿搭</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild className="w-full">
            <Link href="/dashboard/family/feed">
              <Star className="mr-2 h-4 w-4" />
              Open Family Feed
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
