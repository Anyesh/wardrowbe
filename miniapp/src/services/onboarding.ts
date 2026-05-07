import { apiRequest } from './api'
import type { Preferences } from '../shared/types'

export interface OnboardingStepState {
  step_key: string
  status: 'pending' | 'completed' | 'skipped'
}

export interface OnboardingStateResponse {
  is_blocking: boolean
  current_version: string
  current_step: string | null
  active_steps: OnboardingStepState[]
  completed_steps: OnboardingStepState[]
}

export interface StyleQuizQuestion {
  id: string
  title: string
  description?: string
  type: 'single' | 'multi'
  required: boolean
  options: string[]
}

export interface StyleQuizDefinitionResponse {
  step_key: 'style_quiz'
  quiz_version: string
  questions: StyleQuizQuestion[]
}

export interface StyleQuizSubmitResponse {
  updated_preferences: Preferences
  style_insight: string
  next_step: string | null
}

export interface StyleQuizSubmitPayload {
  quiz_version: string
  answers: Record<string, unknown>
}

export function getOnboardingState() {
  return apiRequest<OnboardingStateResponse>('/onboarding/state')
}

export function getStyleQuizDefinition() {
  return apiRequest<StyleQuizDefinitionResponse>('/onboarding/steps/style-quiz')
}

export function submitStyleQuiz(payload: StyleQuizSubmitPayload) {
  return apiRequest<StyleQuizSubmitResponse>('/onboarding/steps/style-quiz/submit', {
    method: 'POST',
    data: payload,
  })
}

export function reopenStyleQuiz() {
  return apiRequest<{ ok: boolean }>('/onboarding/steps/style-quiz/reopen', {
    method: 'POST',
  })
}
