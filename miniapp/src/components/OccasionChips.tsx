import React from 'react'
import { Text, View } from '@tarojs/components'
import { OCCASIONS } from '../shared/constants'

interface OccasionChipsProps {
  value?: string
  onChange: (value: string) => void
}

export default function OccasionChips({ value, onChange }: OccasionChipsProps) {
  return (
    <View className='row-wrap'>
      {OCCASIONS.map((occasion) => (
        <View key={occasion.value} className={`chip ${value === occasion.value ? 'chip--active' : ''}`} onClick={() => onChange(occasion.value)}>
          <Text>{occasion.label}</Text>
        </View>
      ))}
    </View>
  )
}
