export async function register() {
  if (process.env.NEXT_RUNTIME !== 'nodejs') return;

  const { nextauthSecretProblem } = await import('@/lib/startup-checks');
  const problem = nextauthSecretProblem(process.env);
  if (problem) {
    console.error(`Configuration: ${problem}`);
    // Exits instead of throwing because a throw in register() leaves a Next 14.2 server answering 500.
    process.exit(1);
  }
}
