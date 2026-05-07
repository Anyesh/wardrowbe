import React from 'react'
import { Button, Input, Picker, Switch, Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import './index.scss'
import { ONBOARDING_REFRESH_EVENT } from '../../components/OnboardingGate'
import PageHeader from '../../components/PageHeader'
import { reopenStyleQuiz } from '../../services/onboarding'
import { clearAccessToken, getAccessToken, getApiBaseUrl, setApiBaseUrl } from '../../services/session'
import { getPreferences, getUserProfile, syncWeChatMiniapp, updatePreferences, updateUserProfile } from '../../services/user'
import type { Preferences, UserProfile } from '../../shared/types'

const TEMP_UNITS = ['celsius', 'fahrenheit'] as const
const TEMP_SENSITIVITY = ['low', 'normal', 'high'] as const
const LAYERING = ['minimal', 'moderate', 'heavy'] as const
const VARIETY = ['low', 'moderate', 'high'] as const

const DEFAULT_PROFILE: UserProfile = {
  id: '',
  email: '',
  display_name: '',
  timezone: 'UTC',
  role: 'member',
  onboarding_completed: false,
  avatar_url: null,
  location_name: '',
}

const DEFAULT_PREFERENCES: Preferences = {
  color_favorites: [],
  color_avoid: [],
  style_profile: { casual: 50, formal: 50, sporty: 50, minimalist: 50, bold: 50 },
  default_occasion: 'casual',
  temperature_unit: 'celsius',
  temperature_sensitivity: 'normal',
  cold_threshold: 10,
  hot_threshold: 25,
  layering_preference: 'moderate',
  avoid_repeat_days: 7,
  prefer_underused_items: true,
  variety_level: 'moderate',
  ai_endpoints: [],
}

function csvToArray(value: string): string[] {
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

function arrayToCsv(values: string[]): string {
  return values.join(', ')
}

function clampStyleScore(value: number): number {
  return Math.max(0, Math.min(100, value))
}

export default function SettingsPage() {
  const [apiBaseUrl, setApiBaseUrlState] = React.useState('')
  const [token, setToken] = React.useState('')
  const [profile, setProfile] = React.useState<UserProfile | null>(null)
  const [preferences, setPreferences] = React.useState<Preferences | null>(null)
  const [saving, setSaving] = React.useState(false)
  const [aiEndpointJson, setAiEndpointJson] = React.useState('[]')

  const load = React.useCallback(async () => {
    setApiBaseUrlState(getApiBaseUrl())
    setToken(getAccessToken())

    const [nextProfile, nextPreferences] = await Promise.all([
      getUserProfile().catch(() => null),
      getPreferences().catch(() => null),
    ])
    setProfile(nextProfile)
    setPreferences(nextPreferences)
    setAiEndpointJson(JSON.stringify((nextPreferences || DEFAULT_PREFERENCES).ai_endpoints || [], null, 2))
  }, [])

  useDidShow(() => {
    load().catch(() => {
      // keep editable defaults
    })
  })

  const saveSettings = async () => {
    setSaving(true)
    try {
      setApiBaseUrl(apiBaseUrl)

      if (profile) {
        await updateUserProfile({
          display_name: profile.display_name,
          location_name: profile.location_name,
          timezone: profile.timezone,
        })
      }

      const editablePreferences = preferences || DEFAULT_PREFERENCES
      let parsedEndpoints = editablePreferences.ai_endpoints
      try {
        parsedEndpoints = JSON.parse(aiEndpointJson)
        if (!Array.isArray(parsedEndpoints)) {
          throw new Error('AI endpoints must be an array')
        }
      } catch {
        throw new Error('AI 节点配置 JSON 无效')
      }

      await updatePreferences({
        ...editablePreferences,
        ai_endpoints: parsedEndpoints,
      })

      Taro.showToast({ title: '已保存', icon: 'success' })
      setToken(getAccessToken())
      await load()
    } catch (error) {
      Taro.showToast({ title: error instanceof Error ? error.message : '保存失败', icon: 'none' })
    } finally {
      setSaving(false)
    }
  }

  const handleSync = async () => {
    try {
      const response = await syncWeChatMiniapp(profile?.display_name || '微信用户', profile?.avatar_url || undefined)
      setToken(response.access_token)
      Taro.showToast({ title: '已同步', icon: 'success' })
      Taro.eventCenter.trigger(ONBOARDING_REFRESH_EVENT)
      await load()
    } catch (error) {
      Taro.showToast({ title: error instanceof Error ? error.message : '同步失败', icon: 'none' })
    }
  }

  const handleRetakeQuiz = async () => {
    try {
      await reopenStyleQuiz()
      Taro.eventCenter.trigger(ONBOARDING_REFRESH_EVENT)
      Taro.showToast({ title: '已重新开启测评', icon: 'none' })
    } catch (error) {
      Taro.showToast({ title: error instanceof Error ? error.message : '操作失败', icon: 'none' })
    }
  }

  const editableProfile = profile || DEFAULT_PROFILE
  const editablePreferences = preferences || DEFAULT_PREFERENCES

  return (
    <View className='page stack settings-page'>
      <PageHeader title='设置' subtitle='管理连接、账号信息和完整偏好。' />

      <View className='section-card stack settings-page__section'>
        <Text className='section-title'>连接与账号</Text>
        <Input
          className='input'
          value={apiBaseUrl}
          placeholder='https://api.example.com'
          onInput={(event) => setApiBaseUrlState(event.detail.value)}
        />
        <Text className='muted settings-page__token'>当前 Token：{token ? `${token.slice(0, 12)}…` : '未设置'}</Text>
        <View className='row-wrap settings-page__actions'>
          <Button className='secondary-button' onClick={handleSync}>
            微信同步
          </Button>
          <Button
            className='secondary-button'
            onClick={() => {
              clearAccessToken()
              setToken('')
              Taro.eventCenter.trigger(ONBOARDING_REFRESH_EVENT)
            }}
          >
            清除 Token
          </Button>
        </View>
      </View>

      <View className='section-card stack settings-page__section'>
        <Text className='section-title'>个人资料</Text>
        <Input
          className='input'
          value={editableProfile.display_name || ''}
          placeholder='显示名称'
          onInput={(event) => setProfile({ ...editableProfile, display_name: event.detail.value })}
        />
        <Input
          className='input'
          value={editableProfile.location_name || ''}
          placeholder='位置名称'
          onInput={(event) => setProfile({ ...editableProfile, location_name: event.detail.value })}
        />
        <Input
          className='input'
          value={editableProfile.timezone || 'UTC'}
          placeholder='时区'
          onInput={(event) => setProfile({ ...editableProfile, timezone: event.detail.value })}
        />
      </View>

      <View className='section-card stack settings-page__section'>
        <Text className='section-title'>颜色偏好</Text>
        <Input
          className='input'
          value={arrayToCsv(editablePreferences.color_favorites || [])}
          placeholder='喜好颜色，逗号分隔'
          onInput={(event) =>
            setPreferences({
              ...editablePreferences,
              color_favorites: csvToArray(event.detail.value),
            })
          }
        />
        <Input
          className='input'
          value={arrayToCsv(editablePreferences.color_avoid || [])}
          placeholder='避免颜色，逗号分隔'
          onInput={(event) =>
            setPreferences({
              ...editablePreferences,
              color_avoid: csvToArray(event.detail.value),
            })
          }
        />
      </View>

      <View className='section-card stack settings-page__section'>
        <Text className='section-title'>风格权重（0-100）</Text>
        {(['casual', 'formal', 'sporty', 'minimalist', 'bold'] as const).map((key) => (
          <View key={key} className='settings-page__slider-row'>
            <Text className='muted settings-page__field-label'>{key}</Text>
            <Input
              className='input'
              type='number'
              value={String(editablePreferences.style_profile[key] ?? 50)}
              onInput={(event) => {
                const next = clampStyleScore(Number(event.detail.value || 0))
                setPreferences({
                  ...editablePreferences,
                  style_profile: {
                    ...editablePreferences.style_profile,
                    [key]: next,
                  },
                })
              }}
            />
          </View>
        ))}
      </View>

      <View className='section-card stack settings-page__section'>
        <Text className='section-title'>场景与温感</Text>
        <Input
          className='input'
          value={editablePreferences.default_occasion}
          placeholder='默认场景（casual/office/formal等）'
          onInput={(event) =>
            setPreferences({
              ...editablePreferences,
              default_occasion: event.detail.value,
            })
          }
        />

        <View className='settings-page__picker'>
          <Text className='muted'>温度单位</Text>
          <Picker
            mode='selector'
            range={TEMP_UNITS as unknown as string[]}
            value={Math.max(0, TEMP_UNITS.indexOf(editablePreferences.temperature_unit || 'celsius'))}
            onChange={(event) => {
              const next = TEMP_UNITS[Number(event.detail.value)]
              setPreferences({ ...editablePreferences, temperature_unit: next })
            }}
          >
            <View className='input'>
              <Text>{editablePreferences.temperature_unit}</Text>
            </View>
          </Picker>
        </View>

        <View className='settings-page__picker'>
          <Text className='muted'>体感敏感度</Text>
          <Picker
            mode='selector'
            range={TEMP_SENSITIVITY as unknown as string[]}
            value={Math.max(0, TEMP_SENSITIVITY.indexOf(editablePreferences.temperature_sensitivity || 'normal'))}
            onChange={(event) => {
              const next = TEMP_SENSITIVITY[Number(event.detail.value)]
              setPreferences({ ...editablePreferences, temperature_sensitivity: next })
            }}
          >
            <View className='input'>
              <Text>{editablePreferences.temperature_sensitivity}</Text>
            </View>
          </Picker>
        </View>

        <Input
          className='input'
          type='number'
          value={String(editablePreferences.cold_threshold)}
          placeholder='冷阈值'
          onInput={(event) =>
            setPreferences({
              ...editablePreferences,
              cold_threshold: Number(event.detail.value || 0),
            })
          }
        />
        <Input
          className='input'
          type='number'
          value={String(editablePreferences.hot_threshold)}
          placeholder='热阈值'
          onInput={(event) =>
            setPreferences({
              ...editablePreferences,
              hot_threshold: Number(event.detail.value || 0),
            })
          }
        />

        <View className='settings-page__picker'>
          <Text className='muted'>叠穿偏好</Text>
          <Picker
            mode='selector'
            range={LAYERING as unknown as string[]}
            value={Math.max(0, LAYERING.indexOf(editablePreferences.layering_preference || 'moderate'))}
            onChange={(event) => {
              const next = LAYERING[Number(event.detail.value)]
              setPreferences({ ...editablePreferences, layering_preference: next })
            }}
          >
            <View className='input'>
              <Text>{editablePreferences.layering_preference}</Text>
            </View>
          </Picker>
        </View>
      </View>

      <View className='section-card stack settings-page__section'>
        <Text className='section-title'>推荐策略</Text>
        <Input
          className='input'
          type='number'
          value={String(editablePreferences.avoid_repeat_days)}
          placeholder='避免重复天数'
          onInput={(event) =>
            setPreferences({
              ...editablePreferences,
              avoid_repeat_days: Number(event.detail.value || 0),
            })
          }
        />

        <View className='settings-page__picker'>
          <Text className='muted'>变化程度</Text>
          <Picker
            mode='selector'
            range={VARIETY as unknown as string[]}
            value={Math.max(0, VARIETY.indexOf(editablePreferences.variety_level || 'moderate'))}
            onChange={(event) => {
              const next = VARIETY[Number(event.detail.value)]
              setPreferences({ ...editablePreferences, variety_level: next })
            }}
          >
            <View className='input'>
              <Text>{editablePreferences.variety_level}</Text>
            </View>
          </Picker>
        </View>

        <View className='settings-page__switch-row'>
          <Text className='muted'>优先使用低频单品</Text>
          <Switch
            checked={editablePreferences.prefer_underused_items}
            onChange={(event) =>
              setPreferences({
                ...editablePreferences,
                prefer_underused_items: event.detail.value,
              })
            }
          />
        </View>
      </View>

      <View className='section-card stack settings-page__section'>
        <Text className='section-title'>AI 节点配置（JSON）</Text>
        <Textarea
          className='textarea settings-page__json-editor'
          value={aiEndpointJson}
          maxlength={-1}
          onInput={(event) => setAiEndpointJson(event.detail.value)}
        />
      </View>

      <View className='section-card stack settings-page__section'>
        <Text className='section-title'>风格测评</Text>
        <Text className='muted'>重新开启首次风格测评流程。</Text>
        <Button className='secondary-button' onClick={handleRetakeQuiz}>
          重新进行风格测评
        </Button>
      </View>

      <View className='section-card stack settings-page__save'>
        <Text className='muted'>确认无误后保存所有设置。</Text>
        <Button className='primary-button' loading={saving} disabled={saving} onClick={saveSettings}>
          保存设置
        </Button>
      </View>
    </View>
  )
}
