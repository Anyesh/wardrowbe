import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import './index.scss'
import type { AnalyticsResponse, Outfit, UserProfile, WeatherData } from '../../shared/types'
import { formatTemp } from '../../shared/temperature'
import { getOutfits } from '../../services/outfits'
import { getAnalyticsSummary, getUserProfile, getWeather } from '../../services/user'

export default function HomePage() {
  const [profile, setProfile] = React.useState<UserProfile | null>(null)
  const [weather, setWeather] = React.useState<WeatherData | null>(null)
  const [analytics, setAnalytics] = React.useState<AnalyticsResponse | null>(null)
  const [pendingOutfits, setPendingOutfits] = React.useState<Outfit[]>([])
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState('')

  const load = React.useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const nextProfile = await getUserProfile()
      setProfile(nextProfile)

      const [nextAnalytics, nextPending] = await Promise.all([
        getAnalyticsSummary().catch(() => null),
        getOutfits({ status: 'pending', page: 1, pageSize: 3 }).catch(() => ({ outfits: [], total: 0, page: 1, page_size: 3, has_more: false })),
      ])

      setAnalytics(nextAnalytics)
      setPendingOutfits(nextPending.outfits)

      if (nextProfile.location_lat && nextProfile.location_lon) {
        const nextWeather = await getWeather(nextProfile.location_lat, nextProfile.location_lon).catch(() => null)
        setWeather(nextWeather)
      } else {
        setWeather(null)
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }, [])

  useDidShow(() => {
    load()
  })

  return (
    <View className='page stack'>
      <View className='stack'>
        <Text className='muted'>Welcome back</Text>
        <Text className='hero-title'>{profile?.display_name || 'Wardrowbe'}</Text>
      </View>

      {error ? <View className='card'><Text>{error}</Text></View> : null}
      {loading ? <View className='card'><Text>Loading dashboard…</Text></View> : null}

      <View className='card stack'>
        <Text className='section-title'>Weather</Text>
        {weather ? (
          <>
            <Text className='card-title'>{formatTemp(weather.temperature, 'celsius')}</Text>
            <Text className='muted'>Feels like {formatTemp(weather.feels_like, 'celsius')} · {weather.condition}</Text>
          </>
        ) : (
          <Text className='muted'>Set your location in Settings to load local weather.</Text>
        )}
      </View>

      <View className='grid-2'>
        <View className='card stack'>
          <Text className='section-title'>Pending outfits</Text>
          <Text className='card-title'>{pendingOutfits.length}</Text>
          <Text className='muted'>Suggestions waiting for a response</Text>
        </View>
        <View className='card stack'>
          <Text className='section-title'>Wardrobe items</Text>
          <Text className='card-title'>{analytics?.wardrobe.total_items ?? '—'}</Text>
          <Text className='muted'>Ready + processing pieces in your closet</Text>
        </View>
      </View>

      <View className='card stack'>
        <Text className='section-title'>Quick actions</Text>
        <View className='row-wrap'>
          <Button size='mini' onClick={() => Taro.switchTab({ url: '/pages/wardrobe/index' })}>Open wardrobe</Button>
          <Button size='mini' className='button-secondary' onClick={() => Taro.navigateTo({ url: '/pages/wardrobe/add' })}>Add item</Button>
          <Button size='mini' className='button-secondary' onClick={() => Taro.switchTab({ url: '/pages/suggest/index' })}>Suggest outfit</Button>
        </View>
      </View>

      <View className='card stack'>
        <Text className='section-title'>Insights</Text>
        {(analytics?.insights || []).length ? (
          analytics?.insights.map((insight) => <Text key={insight}>• {insight}</Text>)
        ) : (
          <Text className='muted'>Your wardrobe insights will appear here after more activity.</Text>
        )}
      </View>
    </View>
  )
}
