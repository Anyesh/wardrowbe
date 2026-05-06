import React from 'react'
import { Button, Input, Picker, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import './index.scss'
import PageHeader from '../../components/PageHeader'
import BottomActionBar from '../../components/BottomActionBar'
import { clearAccessToken, getAccessToken, getApiBaseUrl, setApiBaseUrl } from '../../services/session'
import { getPreferences, getUserProfile, syncWeChatMiniapp, updatePreferences, updateUserProfile } from '../../services/user'
import type { Preferences, UserProfile } from '../../shared/types'

const TEMP_UNITS = ['celsius', 'fahrenheit'] as const

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

export default function SettingsPage() {
  const [apiBaseUrl, setApiBaseUrlState] = React.useState('')
  const [token, setToken] = React.useState('')
  const [profile, setProfile] = React.useState<UserProfile | null>(null)
  const [preferences, setPreferences] = React.useState<Preferences | null>(null)
  const [saving, setSaving] = React.useState(false)

  const load = React.useCallback(async () => {
    setApiBaseUrlState(getApiBaseUrl())
    setToken(getAccessToken())
    try {
      const [nextProfile, nextPreferences] = await Promise.all([
        getUserProfile().catch(() => null),
        getPreferences().catch(() => null),
      ])
      setProfile(nextProfile)
      setPreferences(nextPreferences)
    } catch {
      // Ignore initial load errors so local setup remains editable.
    }
  }, [])

  useDidShow(() => {
    load()
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
      if (preferences) {
        await updatePreferences({
          temperature_unit: preferences.temperature_unit,
          default_occasion: preferences.default_occasion,
        })
      }
      Taro.showToast({ title: '已保存', icon: 'success' })
      setToken(getAccessToken())
    } catch (error) {
      Taro.showToast({ title: error instanceof Error ? error.message : '保存失败', icon: 'none' })
    } finally {
      setSaving(false)
    }
  }

  const handleSync = async () => {
    try {
      const response = await syncWeChatMiniapp(profile?.display_name || 'WeChat User', profile?.avatar_url || undefined)
      setToken(response.access_token)
      Taro.showToast({ title: '已同步', icon: 'success' })
      await load()
    } catch (error) {
      Taro.showToast({ title: error instanceof Error ? error.message : '同步失败', icon: 'none' })
    }
  }

  const editableProfile = profile || DEFAULT_PROFILE
  const editablePreferences = preferences || DEFAULT_PREFERENCES

  return (
    <View className='page page--with-footer stack settings-page'>
      <PageHeader title='设置' subtitle='管理连接信息、个人资料和偏好设置。' />

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
        <Text className='section-title'>偏好设置</Text>
        <Input
          className='input'
          value={editablePreferences.default_occasion || 'casual'}
          placeholder='默认场景'
          onInput={(event) => setPreferences({ ...editablePreferences, default_occasion: event.detail.value })}
        />
        <View className='settings-page__picker'>
          <Text className='muted'>温度单位</Text>
          <Picker
            mode='selector'
            range={TEMP_UNITS as unknown as string[]}
            value={Math.max(0, TEMP_UNITS.indexOf(editablePreferences.temperature_unit || 'celsius'))}
            onChange={(event) => {
              const nextUnit = TEMP_UNITS[Number(event.detail.value)]
              setPreferences({ ...editablePreferences, temperature_unit: nextUnit })
            }}
          >
            <View className='input'>
              <Text>{editablePreferences.temperature_unit || 'celsius'}</Text>
            </View>
          </Picker>
        </View>
      </View>

      <BottomActionBar>
        <Button className='primary-button' loading={saving} disabled={saving} onClick={saveSettings}>
          保存设置
        </Button>
      </BottomActionBar>
    </View>
  )
}
