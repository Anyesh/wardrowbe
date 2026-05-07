import React from 'react'
import { Button, Text, View } from '@tarojs/components'
import type { StyleQuizDefinitionResponse, StyleQuizQuestion } from '../services/onboarding'
import { getNextQuestionIndex, isQuizComplete, normalizeAnswers, type StyleQuizAnswers } from '../shared/styleQuiz'
import './StyleQuizModal.scss'

interface StyleQuizModalProps {
  definition: StyleQuizDefinitionResponse
  submitting: boolean
  onSubmit: (payload: { quiz_version: string; answers: Record<string, unknown> }) => Promise<void>
}

const OPTION_LABELS: Record<string, string> = {
  casual: '休闲',
  office: '通勤',
  formal: '正式',
  date: '约会',
  sporty: '运动',
  outdoor: '户外',
  minimalist: '极简',
  bold: '个性',
  neutral: '中性色',
  low_saturation: '低饱和',
  bright: '亮色',
  orange: '橙色',
  pink: '粉色',
  purple: '紫色',
  yellow: '黄色',
  green: '绿色',
  red: '红色',
  cold: '怕冷',
  normal: '正常',
  hot: '怕热',
  low: '稳定少变化',
  moderate: '适中',
  high: '多变化',
}

function isQuestionAnswered(question: StyleQuizQuestion, answers: StyleQuizAnswers): boolean {
  const value = (answers as Record<string, unknown>)[question.id]
  if (Array.isArray(value)) return value.length > 0
  return value !== undefined && value !== null && String(value).trim() !== ''
}

export default function StyleQuizModal({ definition, submitting, onSubmit }: StyleQuizModalProps) {
  const [index, setIndex] = React.useState(0)
  const [answers, setAnswers] = React.useState<StyleQuizAnswers>({})

  const question = definition.questions[index]

  const canMoveNext = React.useMemo(() => {
    if (!question.required) return true
    return isQuestionAnswered(question, answers)
  }, [answers, question])

  const complete = React.useMemo(() => {
    const meta = definition.questions.map((q) => ({ id: q.id, required: q.required }))
    return isQuizComplete(meta, normalizeAnswers(answers))
  }, [answers, definition.questions])

  const toggleOption = (option: string) => {
    setAnswers((prev) => {
      const normalized = normalizeAnswers(prev)
      if (question.type === 'multi') {
        const selected = new Set(normalized.avoid_colors || [])
        if (selected.has(option)) {
          selected.delete(option)
        } else {
          selected.add(option)
        }
        return {
          ...normalized,
          [question.id]: Array.from(selected),
          avoid_colors: question.id === 'avoid_colors' ? Array.from(selected) : normalized.avoid_colors,
        }
      }
      return {
        ...normalized,
        [question.id]: option,
      }
    })
  }

  const isOptionActive = (option: string) => {
    const value = (answers as Record<string, unknown>)[question.id]
    if (Array.isArray(value)) return value.includes(option)
    return value === option
  }

  return (
    <View className='style-quiz-modal'>
      <View className='style-quiz-modal__panel'>
        <Text className='style-quiz-modal__title'>先完成穿衣风格测评</Text>
        <Text className='style-quiz-modal__progress'>
          {index + 1}/{definition.questions.length}
        </Text>

        <View className='style-quiz-modal__question'>
          <Text className='style-quiz-modal__question-title'>{question.title}</Text>
          {question.description ? <Text className='style-quiz-modal__question-desc'>{question.description}</Text> : null}
          <View className='style-quiz-modal__options'>
            {question.options.map((option) => (
              <View
                key={option}
                className={`style-quiz-modal__option ${isOptionActive(option) ? 'style-quiz-modal__option--active' : ''}`}
                onClick={() => toggleOption(option)}
              >
                <Text>{OPTION_LABELS[option] || option}</Text>
              </View>
            ))}
          </View>
        </View>

        <View className='style-quiz-modal__actions'>
          <Button
            className='secondary-button style-quiz-modal__action-btn'
            disabled={index === 0 || submitting}
            onClick={() => setIndex((current) => Math.max(0, current - 1))}
          >
            上一题
          </Button>

          {index < definition.questions.length - 1 ? (
            <Button
              className='primary-button style-quiz-modal__action-btn'
              disabled={!canMoveNext || submitting}
              onClick={() => setIndex((current) => getNextQuestionIndex(current, definition.questions.length))}
            >
              下一题
            </Button>
          ) : (
            <Button
              className='primary-button style-quiz-modal__action-btn'
              disabled={!complete || submitting}
              loading={submitting}
              onClick={() =>
                onSubmit({
                  quiz_version: definition.quiz_version,
                  answers: normalizeAnswers(answers) as Record<string, unknown>,
                })
              }
            >
              完成测评
            </Button>
          )}
        </View>
      </View>
    </View>
  )
}
