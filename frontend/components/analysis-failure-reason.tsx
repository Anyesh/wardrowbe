'use client';

import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import type { ApiErrorParams } from '@/lib/api';
import { translateCode, type ErrorTranslator } from '@/lib/errors';

interface AnalysisFailureReasonProps {
  code?: string | null;
  params?: ApiErrorParams | null;
  fallback?: ReactNode;
  className?: string;
}

export function AnalysisFailureReason({
  code,
  params,
  fallback = null,
  className,
}: AnalysisFailureReasonProps) {
  const t = useTranslations('errors') as unknown as ErrorTranslator;
  const reason = translateCode(code, params ?? undefined, t) ?? fallback;
  if (reason === null) return null;
  return <p className={className}>{reason}</p>;
}
