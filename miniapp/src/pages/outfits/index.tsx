import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Input, Picker, Text, View } from '@tarojs/components'
import './index.scss'
import OutfitCard from '../../components/OutfitCard'
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
    load().catch((error) => Taro.showToast({ title: error instanceof Error ? error.message : 'Load failed', icon: 'none' }))
  })

  return (
    <View className='page stack'>
      <Text className='hero-title'>Outfits</Text>
      <Input className='input' value={search} placeholder='Search outfits' onInput={(event) => setSearch(event.detail.value)} onConfirm={() => load()} />
      <View className='row-wrap'>
        {OUTFIT_FILTERS.map((option) => (
          <View key={option.value} className={`chip ${filter === option.value ? 'chip--active' : ''}`} onClick={() => setFilter(option.value)}>
            <Text>{option.label}</Text>
          </View>
        ))}
      </View>
      <Picker mode='date' fields='month' value={month} onChange={(event) => setMonth(event.detail.value)}>
        <View className='input'><Text>{month || 'Select month summary'}</Text></View>
      </Picker>
      <Button size='mini' onClick={() => load()}>Refresh list</Button>
      {outfits.length ? outfits.map((outfit) => (
        <OutfitCard key={outfit.id} outfit={outfit} onClick={() => Taro.navigateTo({ url: `/pages/suggest/result?id=${outfit.id}` })} />
      )) : <View className='card empty-state'><Text>No outfits found for this filter.</Text></View>}
    </View>
  )
}
