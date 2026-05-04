import React from 'react'
import { Picker, Switch, Text, View } from '@tarojs/components'
import { CLOTHING_TYPES } from '../shared/constants'
import type { ItemFilter } from '../shared/types'

interface FilterSheetProps {
  value: ItemFilter
  onChange: (value: ItemFilter) => void
}

const typeOptions = ['All types', ...CLOTHING_TYPES.map((item) => item.label)]

export default function FilterSheet({ value, onChange }: FilterSheetProps) {
  const currentTypeIndex = value.type
    ? Math.max(0, CLOTHING_TYPES.findIndex((item) => item.value === value.type) + 1)
    : 0

  return (
    <View className='card stack'>
      <Text className='section-title'>Filters</Text>
      <View className='row'>
        <Text>Favorites only</Text>
        <Switch checked={Boolean(value.favorite)} onChange={(event) => onChange({ ...value, favorite: event.detail.value })} />
      </View>
      <View className='row'>
        <Text>Needs wash</Text>
        <Switch checked={Boolean(value.needs_wash)} onChange={(event) => onChange({ ...value, needs_wash: event.detail.value })} />
      </View>
      <View className='stack'>
        <Text className='muted'>Item type</Text>
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
