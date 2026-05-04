import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Input, Picker, Text, View } from '@tarojs/components'
import './index.scss'
import ItemCard from '../../components/ItemCard'
import FilterSheet from '../../components/FilterSheet'
import { getItems } from '../../services/items'
import type { Item, ItemFilter } from '../../shared/types'

const SORT_OPTIONS = [
  { label: 'Newest first', value: { sort_by: 'created_at', sort_order: 'desc' as const } },
  { label: 'Oldest first', value: { sort_by: 'created_at', sort_order: 'asc' as const } },
  { label: 'Most worn', value: { sort_by: 'wear_count', sort_order: 'desc' as const } },
]

export default function WardrobePage() {
  const [items, setItems] = React.useState<Item[]>([])
  const [search, setSearch] = React.useState('')
  const [filters, setFilters] = React.useState<ItemFilter>({ sort_by: 'created_at', sort_order: 'desc' })
  const [page, setPage] = React.useState(1)
  const [hasMore, setHasMore] = React.useState(false)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState('')

  const load = React.useCallback(async (nextPage = 1, append = false) => {
    setLoading(true)
    setError('')
    try {
      const response = await getItems({ ...filters, search }, nextPage, 20)
      setItems((current) => (append ? [...current, ...response.items] : response.items))
      setPage(response.page)
      setHasMore(response.has_more)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load wardrobe')
    } finally {
      setLoading(false)
    }
  }, [filters, search])

  useDidShow(() => {
    load(1, false)
  })

  return (
    <View className='page stack'>
      <View className='row'>
        <Text className='hero-title'>Wardrobe</Text>
        <Button size='mini' onClick={() => Taro.navigateTo({ url: '/pages/wardrobe/add' })}>Add</Button>
      </View>

      <Input className='input' value={search} placeholder='Search by name or type' onInput={(event) => setSearch(event.detail.value)} onConfirm={() => load(1, false)} />

      <Picker
        mode='selector'
        range={SORT_OPTIONS.map((option) => option.label)}
        value={Math.max(0, SORT_OPTIONS.findIndex((option) => option.value.sort_by === filters.sort_by && option.value.sort_order === filters.sort_order))}
        onChange={(event) => {
          const next = SORT_OPTIONS[Number(event.detail.value)]
          setFilters((current) => ({ ...current, ...next.value }))
        }}
      >
        <View className='input'><Text>{SORT_OPTIONS.find((option) => option.value.sort_by === filters.sort_by && option.value.sort_order === filters.sort_order)?.label || SORT_OPTIONS[0].label}</Text></View>
      </Picker>

      <FilterSheet value={filters} onChange={setFilters} />

      <View className='row-wrap'>
        <Button size='mini' onClick={() => load(1, false)}>Refresh</Button>
        {hasMore ? <Button size='mini' className='button-secondary' onClick={() => load(page + 1, true)}>Load more</Button> : null}
      </View>

      {error ? <View className='card'><Text>{error}</Text></View> : null}
      {loading && !items.length ? <View className='card'><Text>Loading wardrobe…</Text></View> : null}

      {items.length ? (
        <View className='grid-2'>
          {items.map((item) => (
            <ItemCard key={item.id} item={item} onClick={() => Taro.navigateTo({ url: `/pages/wardrobe/detail?id=${item.id}` })} />
          ))}
        </View>
      ) : (
        <View className='card empty-state'>
          <Text>No items yet. Add your first piece to start the wardrobe flow.</Text>
        </View>
      )}
    </View>
  )
}
