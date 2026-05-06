import React from 'react'
import { Image, Text, View } from '@tarojs/components'
import type { Item } from '../shared/types'
import { joinList, titleCase } from '../shared/format'

interface ItemCardProps {
  item: Item
  onClick?: () => void
}

export default function ItemCard({ item, onClick }: ItemCardProps) {
  return (
    <View className='item-card section-card' onClick={onClick}>
      <Image
        className='item-card__image'
        src={item.thumbnail_url || item.image_url || item.thumbnail_path || item.image_path}
        mode='aspectFill'
      />
      <View className='stack item-card__body'>
        <View className='row item-card__headline'>
          <Text className='card-title'>{item.name || titleCase(item.type)}</Text>
          {item.favorite ? <Text className='badge'>★</Text> : null}
        </View>
        <Text className='muted'>{joinList([titleCase(item.type), item.primary_color ? titleCase(item.primary_color) : undefined])}</Text>
        <View className='row-wrap item-card__meta'>
          <Text className={`badge ${item.status === 'ready' ? 'badge--ok' : ''}`}>{titleCase(item.status)}</Text>
          {item.needs_wash ? <Text className='badge badge--warn'>需要清洗</Text> : null}
        </View>
      </View>
    </View>
  )
}
