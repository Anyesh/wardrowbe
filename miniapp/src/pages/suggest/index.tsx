import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Input, Text, View } from '@tarojs/components'
import './index.scss'
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
    load().catch((error) => Taro.showToast({ title: error instanceof Error ? error.message : 'Load failed', icon: 'none' }))
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
      Taro.showToast({ title: error instanceof Error ? error.message : 'Suggestion failed', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <View className='page stack'>
      <Text className='hero-title'>Suggest an outfit</Text>
      <View className='card stack'>
        <Text className='section-title'>Weather context</Text>
        <Text>{weather ? `${formatTemp(weather.temperature, preferences?.temperature_unit || 'celsius')} · ${weather.condition}` : 'Weather will use your saved location.'}</Text>
        <Input className='input' value={temperatureOverride} placeholder='Optional override temperature (°C)' onInput={(event) => setTemperatureOverride(event.detail.value)} />
      </View>
      <View className='card stack'>
        <Text className='section-title'>Occasion</Text>
        <OccasionChips value={occasion} onChange={setOccasion} />
      </View>
      <Button loading={loading} onClick={generate}>Generate outfit</Button>
      {profile?.location_name ? <Text className='muted'>Using location: {profile.location_name}</Text> : null}
    </View>
  )
}
