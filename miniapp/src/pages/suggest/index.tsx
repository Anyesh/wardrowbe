import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Input, Text, View } from '@tarojs/components'
import './index.scss'
import BottomActionBar from '../../components/BottomActionBar'
import PageHeader from '../../components/PageHeader'
import OccasionChips from '../../components/OccasionChips'
import { setLastSuggestionId } from '../../services/session'
import { suggestOutfit } from '../../services/outfits'
import { getPreferences, getUserProfile, getWeather } from '../../services/user'
import type { Preferences, UserProfile, WeatherData } from '../../shared/types'
import { formatTemp } from '../../shared/temperature'

export default function SuggestPage() {
  const [profile, setProfile] = React.useState<UserProfile | null>(null)
  const [preferences, setPreferences] = React.useState<Preferences | null>(null)
  const [weather, setWeather] = React.useState<WeatherData | null>(null)
  const [occasion, setOccasion] = React.useState('casual')
  const [temperatureOverride, setTemperatureOverride] = React.useState('')
  const [loading, setLoading] = React.useState(false)

  const load = React.useCallback(async () => {
    const [nextProfile, nextPreferences] = await Promise.all([getUserProfile(), getPreferences()])
    setProfile(nextProfile)
    setPreferences(nextPreferences)
    setOccasion(nextPreferences.default_occasion || 'casual')
    if (nextProfile.location_lat && nextProfile.location_lon) {
      setWeather(await getWeather(nextProfile.location_lat, nextProfile.location_lon).catch(() => null))
    }
  }, [])

  useDidShow(() => {
    load().catch((error) => Taro.showToast({ title: error instanceof Error ? error.message : '加载失败', icon: 'none' }))
  })

  const generate = async () => {
    setLoading(true)
    try {
      const nextOutfit = await suggestOutfit({
        occasion,
        weather_override: temperatureOverride
          ? {
              temperature: Number(temperatureOverride),
              humidity: weather?.humidity || 50,
              precipitation_chance: weather?.precipitation_chance || 0,
              condition: weather?.condition || 'unknown',
            }
          : undefined,
      })
      setLastSuggestionId(nextOutfit.id)
      Taro.navigateTo({ url: `/pages/suggest/result?id=${nextOutfit.id}` })
    } catch (error) {
      Taro.showToast({ title: error instanceof Error ? error.message : '生成建议失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <View className='page page--with-footer stack suggest-page'>
      <PageHeader
        eyebrow='Suggest'
        title='生成穿搭建议'
        subtitle={profile?.location_name ? `当前位置：${profile.location_name}` : undefined}
      />

      <View className='section-card stack'>
        <Text className='section-title'>上下文</Text>
        <Text className='card-subtitle'>
          {weather
            ? `${formatTemp(weather.temperature, preferences?.temperature_unit || 'celsius')} · ${weather.condition}`
            : '将使用你在设置中保存的位置天气。'}
        </Text>
      </View>

      <View className='section-card stack suggest-page__occasion'>
        <Text className='section-title'>场景</Text>
        <OccasionChips value={occasion} onChange={setOccasion} />
      </View>

      <View className='section-card stack'>
        <Text className='section-title'>可选：覆盖温度</Text>
        <Input
          className='input'
          value={temperatureOverride}
          placeholder='输入温度（°C）'
          onInput={(event) => setTemperatureOverride(event.detail.value)}
        />
        <Text className='muted'>用于临时测试或当天气与体感差异较大时手动调整。</Text>
      </View>

      <BottomActionBar>
        <Button className='primary-button' loading={loading} disabled={loading} onClick={generate}>
          生成穿搭
        </Button>
      </BottomActionBar>
    </View>
  )
}
