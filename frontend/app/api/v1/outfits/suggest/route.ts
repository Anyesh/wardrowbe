import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://backend:8000';

export async function POST(request: NextRequest) {
  const body = await request.text();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const auth = request.headers.get('Authorization');
  if (auth) headers['Authorization'] = auth;

  try {
    const response = await fetch(`${BACKEND_URL}/api/v1/outfits/suggest`, {
      method: 'POST',
      headers,
      body,
    });

    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch {
    return NextResponse.json({ detail: 'An error occurred' }, { status: 500 });
  }
}
