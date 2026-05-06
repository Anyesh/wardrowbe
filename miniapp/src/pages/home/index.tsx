import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import './index.scss'
import PageHeader from '../../components/PageHeader'
import StatCard from '../../components/StatCard'
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
    <View className='page stack home-page'>
      <PageHeader
        eyebrow='Welcome back'
        title={profile?.display_name || 'Wardrowbe'}
        subtitle={profile?.location_name ? `当前位置：${profile.location_name}` : undefined}
      />

      {error ? (
        <View className='section-card'>
          <Text>{error}</Text>
        </View>
      ) : null}
      {loading ? (
        <View className='section-card'>
          <Text>正在加载首页…</Text>
        </View>
      ) : null}

      <View className='section-card stack'>
        <Text className='section-title'>Today</Text>
        {weather ? (
          <>
            <Text className='hero-title'>{formatTemp(weather.temperature, 'celsius')}</Text>
            <Text className='muted'>体感 {formatTemp(weather.feels_like, 'celsius')} · {weather.condition}</Text>
          </>
        ) : (
          <Text className='muted'>请先在设置里填写位置，以便加载本地天气。</Text>
        )}
      </View>

      <View className='grid-2'>
        <StatCard label='待处理穿搭' value={pendingOutfits.length} hint='等待你反馈的穿搭建议' />
        <StatCard label='衣橱单品' value={analytics?.wardrobe.total_items ?? '—'} hint='衣橱中可穿与处理中单品总数' />
      </View>

      <View className='section-card stack home-page__actions'>
        <Text className='section-title'>Quick actions</Text>
        <Button className='primary-button' onClick={() => Taro.switchTab({ url: '/pages/suggest/index' })}>
          生成今日穿搭
        </Button>
        <View className='grid-2 home-page__actions-grid'>
          <Button className='secondary-button' onClick={() => Taro.switchTab({ url: '/pages/wardrobe/index' })}>
            浏览衣橱
          </Button>
          <Button className='secondary-button' onClick={() => Taro.navigateTo({ url: '/pages/wardrobe/add' })}>
            添加单品
          </Button>
        </View>
      </View>

      <View className='section-card stack'>
        <Text className='section-title'>Insights</Text>
        {(analytics?.insights || []).length
          ? analytics?.insights.map((insight) => (
              <Text key={insight} className='home-page__insight'>
                • {insight}
              </Text>
            ))
          : <Text className='muted'>有更多穿搭活动后，这里会显示你的衣橱洞察。</Text>}
      </View>
    </View>
  )
}
