import React from 'react'
import Taro from '@tarojs/taro'
import { Text, View } from '@tarojs/components'
import {
  getOnboardingState,
  getStyleQuizDefinition,
  submitStyleQuiz,
  type OnboardingStateResponse,
  type StyleQuizDefinitionResponse,
} from '../services/onboarding'
import { getAccessToken } from '../services/session'
import { shouldBlockApp } from '../shared/styleQuiz'
import StyleQuizModal from './StyleQuizModal'
import './OnboardingGate.scss'

export const ONBOARDING_REFRESH_EVENT = 'onboarding:refresh'

export default function OnboardingGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<OnboardingStateResponse | null>(null)
  const [definition, setDefinition] = React.useState<StyleQuizDefinitionResponse | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [submitting, setSubmitting] = React.useState(false)

  const refresh = React.useCallback(async () => {
    if (!getAccessToken()) {
      setState(null)
      setDefinition(null)
      return
    }

    setLoading(true)
    try {
      const nextState = await getOnboardingState()
      setState(nextState)

      if (shouldBlockApp(nextState)) {
        const quiz = await getStyleQuizDefinition()
        setDefinition(quiz)
      } else {
        setDefinition(null)
      }
    } catch {
      // Silent fallback: onboarding should never block app if state endpoint fails.
      setState(null)
      setDefinition(null)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    refresh()

    const refreshHandler = () => {
      refresh()
    }

    Taro.eventCenter.on(ONBOARDING_REFRESH_EVENT, refreshHandler)

    const appShowHandler = () => {
      refresh()
    }

    Taro.onAppShow(appShowHandler)

    return () => {
      Taro.eventCenter.off(ONBOARDING_REFRESH_EVENT, refreshHandler)
      if (typeof Taro.offAppShow === 'function') {
        Taro.offAppShow(appShowHandler)
      }
    }
  }, [refresh])

  const handleSubmit = async (payload: { quiz_version: string; answers: Record<string, unknown> }) => {
    setSubmitting(true)
    try {
      const response = await submitStyleQuiz(payload)
      if (response.style_insight) {
        Taro.showToast({
          title: response.style_insight.slice(0, 18),
          icon: 'none',
          duration: 2200,
        })
      }
      await refresh()
    } catch (error) {
      Taro.showToast({
        title: error instanceof Error ? error.message : '提交测评失败',
        icon: 'none',
      })
    } finally {
      setSubmitting(false)
    }
  }

  const blocked = shouldBlockApp(state)

  return (
    <View className='onboarding-gate-root'>
      {children}
      {blocked && definition ? (
        <StyleQuizModal definition={definition} submitting={submitting} onSubmit={handleSubmit} />
      ) : null}
      {blocked && loading ? (
        <View className='onboarding-gate-loading'>
          <Text>正在准备风格测评…</Text>
        </View>
      ) : null}
    </View>
  )
}
