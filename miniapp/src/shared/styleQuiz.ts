import type { OnboardingStateResponse } from '../services/onboarding'

export interface QuizQuestionMeta {
  id: string
  required: boolean
}

export interface StyleQuizAnswers {
  primary_occasion?: string
  style_focus?: string
  color_palette?: string
  avoid_colors?: string[]
  temperature_feel?: string
  variety?: string
}

export function normalizeAnswers(answers: Partial<StyleQuizAnswers>): StyleQuizAnswers {
  const avoid = answers.avoid_colors
  return {
    ...answers,
    avoid_colors: Array.isArray(avoid) ? avoid : avoid ? [String(avoid)] : [],
  }
}

export function isQuizComplete(questions: QuizQuestionMeta[], answers: Partial<StyleQuizAnswers>): boolean {
  return questions.every((question) => {
    if (!question.required) return true
    const value = (answers as Record<string, unknown>)[question.id]
    if (Array.isArray(value)) return value.length > 0
    return value !== undefined && value !== null && String(value).trim() !== ''
  })
}

export function getNextQuestionIndex(current: number, total: number): number {
  return Math.min(current + 1, Math.max(total - 1, 0))
}

export function shouldBlockApp(state: OnboardingStateResponse | null): boolean {
  if (!state) return false
  return state.is_blocking && state.current_step === 'style_quiz'
}
