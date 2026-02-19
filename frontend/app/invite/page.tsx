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

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return 'This invite link is invalid or has expired.';
    if (error.status === 403) return 'This invite was sent to a different email address.';
    if (error.status === 409) return 'You are already in a family.';
  }
  return 'Something went wrong. Please try again.';
}

function InviteContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { status } = useSession();
  const token = searchParams.get('token');
  const joinByToken = useJoinFamilyByToken();

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
      toast.success(`Joined ${result.family_name}!`);
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
            Family Invitation
          </CardTitle>
          <CardDescription>
            You&apos;ve been invited to join a family on Wardrowbe
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {joinByToken.isError && (
            <p className="text-sm text-destructive">{getErrorMessage(joinByToken.error)}</p>
          )}
          <Button
            onClick={handleAccept}
            className="w-full"
            disabled={joinByToken.isPending || joinByToken.isSuccess}
          >
            {joinByToken.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Accept Invitation
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
