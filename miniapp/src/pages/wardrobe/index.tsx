import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Input, Picker, Text, View } from '@tarojs/components'
import './index.scss'
import PageHeader from '../../components/PageHeader'
import ItemCard from '../../components/ItemCard'
import FilterSheet from '../../components/FilterSheet'
import EmptyState from '../../components/EmptyState'
import { getItems } from '../../services/items'
import type { Item, ItemFilter } from '../../shared/types'

const SORT_OPTIONS = [
  { label: '最新优先', value: { sort_by: 'created_at', sort_order: 'desc' as const } },
  { label: '最早优先', value: { sort_by: 'created_at', sort_order: 'asc' as const } },
  { label: '穿着次数最多', value: { sort_by: 'wear_count', sort_order: 'desc' as const } },
]

export default function 衣橱Page() {
  const [items, setItems] = React.useState<Item[]>([])
  const [search, setSearch] = React.useState('')
  const [filters, setFilters] = React.useState<ItemFilter>({ sort_by: 'created_at', sort_order: 'desc' })
  const [page, setPage] = React.useState(1)
  const [hasMore, setHasMore] = React.useState(false)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState('')
  const [showFilters, setShowFilters] = React.useState(false)

  const load = React.useCallback(async (nextPage = 1, append = false, overrides?: { filters?: ItemFilter; search?: string }) => {
    setLoading(true)
    setError('')
    try {
      const response = await getItems({ ...(overrides?.filters ?? filters), search: overrides?.search ?? search }, nextPage, 20)
      setItems((current) => (append ? [...current, ...response.items] : response.items))
      setPage(response.page)
      setHasMore(response.has_more)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '加载衣橱失败')
    } finally {
      setLoading(false)
    }
  }, [filters, search])

  const applyFilters = (next: ItemFilter) => {
    setFilters(next)
    load(1, false, { filters: next })
  }

  const activeFilterCount = React.useMemo(() => {
    const entries = [filters.type, filters.favorite, filters.needs_wash]
    return entries.filter((value) => value !== undefined && value !== null && value !== '').length
  }, [filters.favorite, filters.needs_wash, filters.type])

  useDidShow(() => {
    load(1, false)
  })

  return (
    <View className='page stack wardrobe-page'>
      <PageHeader
        title='衣橱'
        subtitle='浏览单品、筛选状态、快速进入详情。'
        rightSlot={(
          <Button className='primary-button' onClick={() => Taro.navigateTo({ url: '/pages/wardrobe/add' })}>
            添加单品
          </Button>
        )}
      />

      <Input
        className='input'
        value={search}
        confirmType='search'
        placeholder='按名称、类型或颜色搜索'
        onInput={(event) => setSearch(event.detail.value)}
        onConfirm={() => load(1, false)}
      />

      <View className='wardrobe-page__toolbar'>
        <View className='wardrobe-page__summary row'>
          <Picker
            mode='selector'
            range={SORT_OPTIONS.map((option) => option.label)}
            value={Math.max(
              0,
              SORT_OPTIONS.findIndex(
                (option) => option.value.sort_by === filters.sort_by && option.value.sort_order === filters.sort_order,
              ),
            )}
            onChange={(event) => {
              const next = SORT_OPTIONS[Number(event.detail.value)]
              applyFilters({ ...filters, ...next.value })
            }}
          >
            <View className='chip wardrobe-page__chip'>
              <Text>
                {SORT_OPTIONS.find(
                  (option) => option.value.sort_by === filters.sort_by && option.value.sort_order === filters.sort_order,
                )?.label || SORT_OPTIONS[0].label}
              </Text>
            </View>
          </Picker>

          <View className='row wardrobe-page__summary-right'>
            <View
              className='chip wardrobe-page__chip wardrobe-page__chip--clickable'
              onClick={() => setShowFilters((current) => !current)}
            >
              <Text>{activeFilterCount ? `筛选（${activeFilterCount}）` : '筛选'}</Text>
            </View>
          </View>
        </View>

        {showFilters ? <FilterSheet value={filters} onChange={applyFilters} /> : null}
      </View>

      {error ? (
        <View className='section-card'>
          <Text className='muted'>{error}</Text>
          <View className='row-wrap wardrobe-page__error-actions'>
            <Button className='secondary-button' onClick={() => load(1, false)}>
              重试
            </Button>
          </View>
        </View>
      ) : null}

      {loading && !items.length ? (
        <View className='section-card'>
          <Text className='muted'>正在加载衣橱…</Text>
        </View>
      ) : null}

      {items.length ? (
        <View className='grid-2 wardrobe-page__grid'>
          {items.map((item) => (
            <ItemCard key={item.id} item={item} onClick={() => Taro.navigateTo({ url: `/pages/wardrobe/detail?id=${item.id}` })} />
          ))}
        </View>
      ) : (
        <EmptyState
          title='衣橱还是空的'
          description='先添加第一件单品，后续才能生成更准确的穿搭建议。'
          action={(
            <Button className='primary-button' onClick={() => Taro.navigateTo({ url: '/pages/wardrobe/add' })}>
              添加第一件单品
            </Button>
          )}
        />
      )}

      {items.length ? (
        <View className='wardrobe-page__load-more'>
          {hasMore ? (
            <Button
              className='secondary-button'
              disabled={loading}
              onClick={() => load(page + 1, true)}
            >
              {loading ? '加载中…' : '加载更多'}
            </Button>
          ) : (
            <Text className='muted'>{loading ? '加载中…' : '已经到底啦'}</Text>
          )}

          <Text
            className='muted wardrobe-page__load-more-refresh'
            onClick={() => {
              if (!loading) load(1, false)
            }}
          >
            刷新列表
          </Text>
        </View>
      ) : null}
    </View>
  )
}
