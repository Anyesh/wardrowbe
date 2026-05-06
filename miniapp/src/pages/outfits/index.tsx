import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Input, Picker, ScrollView, Text, View } from '@tarojs/components'
import './index.scss'
import EmptyState from '../../components/EmptyState'
import OutfitCard from '../../components/OutfitCard'
import PageHeader from '../../components/PageHeader'
import { OUTFIT_FILTERS } from '../../shared/constants'
import { getOutfits } from '../../services/outfits'
import type { Outfit } from '../../shared/types'

export default function OutfitsPage() {
  const [outfits, setOutfits] = React.useState<Outfit[]>([])
  const [search, setSearch] = React.useState('')
  const [filter, setFilter] = React.useState('all')
  const [month, setMonth] = React.useState('')

  const load = React.useCallback(async () => {
    const params = filter === 'all'
      ? {}
      : filter === 'lookbook'
        ? { is_lookbook: true }
        : filter === 'accepted'
          ? { status: 'accepted' }
          : filter === 'pairing'
            ? { source: 'pairing' }
            : filter === 'replacement'
              ? { is_replacement: true }
              : { source: 'on_demand,scheduled' }

    const response = await getOutfits({ ...params, search, page: 1, pageSize: 20 })
    setOutfits(response.outfits)
  }, [filter, search])

  useDidShow(() => {
    load().catch((error) => Taro.showToast({ title: error instanceof Error ? error.message : '加载失败', icon: 'none' }))
  })

  return (
    <View className='page stack outfits-page'>
      <PageHeader
        eyebrow='Outfits'
        title='穿搭'
        subtitle='浏览、搜索并筛选历史穿搭'
      />

      <Input
        className='input'
        value={search}
        placeholder='搜索穿搭'
        onInput={(event) => setSearch(event.detail.value)}
        onConfirm={() => load()}
      />

      <ScrollView className='outfits-page__filters' scrollX enableFlex showScrollbar={false}>
        <View className='outfits-page__filters-inner'>
          {OUTFIT_FILTERS.map((option) => (
            <View
              key={option.value}
              className={`chip ${filter === option.value ? 'chip--active' : ''}`}
              onClick={() => setFilter(option.value)}
            >
              <Text>{option.label}</Text>
            </View>
          ))}
        </View>
      </ScrollView>

      <View className='row outfits-page__month'>
        <View className='outfits-page__month-picker'>
          <Picker mode='date' fields='month' value={month} onChange={(event) => setMonth(event.detail.value)}>
            <View className='input'>
              <Text>{month || '选择月份概览'}</Text>
            </View>
          </Picker>
        </View>
        <Button className='secondary-button outfits-page__month-button' onClick={() => load()}>
          刷新
        </Button>
      </View>

      {outfits.length
        ? outfits.map((outfit) => (
            <OutfitCard
              key={outfit.id}
              outfit={outfit}
              onClick={() => Taro.navigateTo({ url: `/pages/suggest/result?id=${outfit.id}` })}
            />
          ))
        : (
            <EmptyState
              title='还没有符合条件的穿搭'
              description='调整筛选条件，或者先去 Suggest 生成一套新的穿搭。'
              action={
                <Button className='primary-button' onClick={() => Taro.switchTab({ url: '/pages/suggest/index' })}>
                  去生成穿搭
                </Button>
              }
            />
          )}
    </View>
  )
}
