'use client';

import { Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { toast } from 'sonner';
import { Loader2, UserPlus } from 'lucide-react';
import { useSession } from 'next-auth/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useJoinFamilyByToken } from '@/lib/hooks/use-family';
import { ApiError } from '@/lib/api';
import { useTranslations } from 'next-intl';

function getErrorMessage(error: unknown, t: (key: string) => string): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return t('invite.invalidLink');
    if (error.status === 403) return t('invite.wrongEmail');
    if (error.status === 409) return t('invite.alreadyInFamily');
  }
  return t('default');
}

function InviteContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { status } = useSession();
  const token = searchParams.get('token');
  const joinByToken = useJoinFamilyByToken();
  const t = useTranslations('auth');
  const te = useTranslations('errors');

  useEffect(() => {
    if (!token) {
      router.replace('/dashboard/family');
    } else if (status === 'unauthenticated') {
      router.replace(`/login?callbackUrl=${encodeURIComponent(`/invite?token=${token}`)}`);
    }
  }, [status, router, token]);

  if (!token) {
    return null;
  }

  if (status === 'loading' || status === 'unauthenticated') {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const handleAccept = async () => {
    try {
      const result = await joinByToken.mutateAsync(token);
      toast.success(t('invite.joinedFamily', { name: result.family_name }));
      router.push('/dashboard/family');
    } catch {
      // error displayed via joinByToken.error below
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UserPlus className="h-5 w-5" />
            {t('invite.title')}
          </CardTitle>
          <CardDescription>
            {t('invite.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {joinByToken.isError && (
            <p className="text-sm text-destructive">{getErrorMessage(joinByToken.error, te)}</p>
          )}
          <Button
            onClick={handleAccept}
            className="w-full"
            disabled={joinByToken.isPending || joinByToken.isSuccess}
          >
            {joinByToken.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('invite.acceptButton')}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default function InvitePage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      }
    >
      <InviteContent />
    </Suspense>
  );
}
