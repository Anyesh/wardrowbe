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
    <View className='card stack' onClick={onClick}>
      <Image
        className='item-card__image'
        src={item.thumbnail_url || item.image_url || item.thumbnail_path || item.image_path}
        mode='aspectFill'
      />
      <View className='stack item-card__body'>
        <View className='row'>
          <Text className='card-title'>{item.name || titleCase(item.type)}</Text>
          {item.favorite ? <Text className='badge'>★</Text> : null}
        </View>
        <Text className='muted'>{joinList([titleCase(item.type), item.primary_color ? titleCase(item.primary_color) : undefined])}</Text>
        <View className='row-wrap'>
          <Text className={`badge ${item.status === 'ready' ? 'badge--ok' : ''}`}>{titleCase(item.status)}</Text>
          {item.needs_wash ? <Text className='badge badge--warn'>Needs wash</Text> : null}
        </View>
      </View>
    </View>
  )
}
