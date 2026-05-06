import React from 'react'
import { Button, Picker, Switch, Text, View } from '@tarojs/components'
import { CLOTHING_TYPES } from '../shared/constants'
import type { ItemFilter } from '../shared/types'

interface FilterSheetProps {
  value: ItemFilter
  onChange: (value: ItemFilter) => void
}

const typeOptions = ['全部类型', ...CLOTHING_TYPES.map((item) => item.label)]

export default function FilterSheet({ value, onChange }: FilterSheetProps) {
  const currentTypeIndex = value.type
    ? Math.max(0, CLOTHING_TYPES.findIndex((item) => item.value === value.type) + 1)
    : 0

  return (
    <View className='filter-sheet section-card stack'>
      <View className='row'>
        <Text className='section-title'>筛选</Text>
        <Button
          className='secondary-button'
          size='mini'
          onClick={() =>
            onChange({
              ...value,
              favorite: undefined,
              needs_wash: undefined,
              type: undefined,
            })
          }
        >
          重置
        </Button>
      </View>

      <View className='filter-sheet__group stack'>
        <Text className='muted'>偏好</Text>
        <View className='row'>
          <Text>仅看收藏</Text>
          <Switch checked={Boolean(value.favorite)} onChange={(event) => onChange({ ...value, favorite: event.detail.value })} />
        </View>
        <View className='row'>
          <Text>需要清洗</Text>
          <Switch checked={Boolean(value.needs_wash)} onChange={(event) => onChange({ ...value, needs_wash: event.detail.value })} />
        </View>
      </View>

      <View className='filter-sheet__group stack'>
        <Text className='muted'>类型</Text>
        <Picker
          mode='selector'
          range={typeOptions}
          value={currentTypeIndex}
          onChange={(event) => {
            const nextIndex = Number(event.detail.value)
            onChange({
              ...value,
              type: nextIndex === 0 ? undefined : CLOTHING_TYPES[nextIndex - 1]?.value,
            })
          }}
        >
          <View className='input'>
            <Text>{typeOptions[currentTypeIndex]}</Text>
          </View>
        </Picker>
      </View>
    </View>
  )
}
