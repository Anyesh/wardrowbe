import React from 'react'
import { Button, Input, Picker, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import './index.scss'
import { getAccessToken, setApiBaseUrl, getApiBaseUrl, clearAccessToken } from '../../services/session'
import { getPreferences, getUserProfile, syncWeChatMiniapp, updatePreferences, updateUserProfile } from '../../services/user'
import type { Preferences, UserProfile } from '../../shared/types'

const TEMP_UNITS = ['celsius', 'fahrenheit'] as const

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
      // ignore initial load errors here; page remains editable for local debug setup
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

  return (
    <View className='page stack'>
      <View className='card stack'>
        <Text className='section-title'>连接设置</Text>
        <Input className='input' value={apiBaseUrl} placeholder='https://api.example.com' onInput={(event) => setApiBaseUrlState(event.detail.value)} />
        <Text className='muted'>当前 Token：{token ? `${token.slice(0, 12)}…` : '未设置'}</Text>
        <View className='row-wrap'>
          <Button size='mini' onClick={handleSync}>微信同步</Button>
          <Button size='mini' className='button-secondary' onClick={() => { clearAccessToken(); setToken('') }}>清除 Token</Button>
        </View>
      </View>

      <View className='card stack'>
        <Text className='section-title'>个人资料</Text>
        <Input className='input' value={profile?.display_name || ''} placeholder='显示名称' onInput={(event) => setProfile((current) => ({ ...(current || { id: '', email: '', display_name: '', timezone: 'UTC', role: 'member', onboarding_completed: false }), display_name: event.detail.value }))} />
        <Input className='input' value={profile?.location_name || ''} placeholder='位置名称' onInput={(event) => setProfile((current) => ({ ...(current || { id: '', email: '', display_name: '', timezone: 'UTC', role: 'member', onboarding_completed: false }), location_name: event.detail.value }))} />
        <Input className='input' value={profile?.timezone || 'UTC'} placeholder='时区' onInput={(event) => setProfile((current) => ({ ...(current || { id: '', email: '', display_name: '', timezone: 'UTC', role: 'member', onboarding_completed: false }), timezone: event.detail.value }))} />
      </View>

      <View className='card stack'>
        <Text className='section-title'>Preferences</Text>
        <Input className='input' value={preferences?.default_occasion || 'casual'} placeholder='默认场景' onInput={(event) => setPreferences((current) => ({ ...(current || { color_favorites: [], color_avoid: [], style_profile: { casual: 50, formal: 50, sporty: 50, minimalist: 50, bold: 50 }, default_occasion: 'casual', temperature_unit: 'celsius', temperature_sensitivity: 'normal', cold_threshold: 10, hot_threshold: 25, layering_preference: 'moderate', avoid_repeat_days: 7, prefer_underused_items: true, variety_level: 'moderate', ai_endpoints: [] }), default_occasion: event.detail.value }))} />
        <Picker
          mode='selector'
          range={TEMP_UNITS as unknown as string[]}
          value={Math.max(0, TEMP_UNITS.indexOf(preferences?.temperature_unit || 'celsius'))}
          onChange={(event) => {
            const nextUnit = TEMP_UNITS[Number(event.detail.value)]
            setPreferences((current) => ({ ...(current || { color_favorites: [], color_avoid: [], style_profile: { casual: 50, formal: 50, sporty: 50, minimalist: 50, bold: 50 }, default_occasion: 'casual', temperature_unit: 'celsius', temperature_sensitivity: 'normal', cold_threshold: 10, hot_threshold: 25, layering_preference: 'moderate', avoid_repeat_days: 7, prefer_underused_items: true, variety_level: 'moderate', ai_endpoints: [] }), temperature_unit: nextUnit }))
          }}
        >
          <View className='input'><Text>{preferences?.temperature_unit || 'celsius'}</Text></View>
        </Picker>
      </View>

      <Button loading={saving} onClick={saveSettings}>保存设置</Button>
    </View>
  )
}
