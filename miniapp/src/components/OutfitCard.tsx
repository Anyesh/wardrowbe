import React from 'react'
import { Image, Text, View } from '@tarojs/components'
import type { Outfit } from '../shared/types'
import { formatDate, titleCase } from '../shared/format'

interface OutfitCardProps {
  outfit: Outfit
  onClick?: () => void
}

export default function OutfitCard({ outfit, onClick }: OutfitCardProps) {
  return (
    <View className='outfit-card section-card' onClick={onClick}>
      <View className='row'>
        <Text className='card-title'>{titleCase(outfit.occasion)}</Text>
        <Text className='badge'>{titleCase(outfit.status)}</Text>
      </View>
      <Text className='muted'>Created {formatDate(outfit.created_at)}</Text>
      <View className='thumb-strip'>
        {outfit.items.slice(0, 4).map((item) => (
          <Image
            key={item.id}
            className='thumb-strip__image'
            src={item.thumbnail_url || item.image_url || item.thumbnail_path || item.image_path || ''}
            mode='aspectFill'
          />
        ))}
      </View>
      {outfit.reasoning ? <Text className='outfit-card__summary'>{outfit.reasoning}</Text> : null}
    </View>
  )
}
