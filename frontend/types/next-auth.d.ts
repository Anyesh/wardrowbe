import 'next-auth';
import 'next-auth/jwt';

declare module 'next-auth' {
  interface User {
    accessToken?: string;
    backendUserId?: string;
    isNewUser?: boolean;
    onboardingCompleted?: boolean;
  }

  interface Session {
    user: {
      id?: string;
      name?: string | null;
      email?: string | null;
      image?: string | null;
    };
    accessToken?: string;
    isNewUser?: boolean;
    onboardingCompleted?: boolean;
    syncError?: string;
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    accessToken?: string;
    sub?: string;
    backendUserId?: string;
    isNewUser?: boolean;
    onboardingCompleted?: boolean;
    syncError?: string;
  }
}
