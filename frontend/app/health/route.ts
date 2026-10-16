import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

// Liveness probe for the frontend container; reveals nothing about the install.
export function GET() {
  return NextResponse.json({ status: 'healthy' });
}
