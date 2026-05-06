import React from 'react'
import { Text, View } from '@tarojs/components'

interface EmptyStateProps {
  title: string
  description: string
  action?: React.ReactNode
}

export default function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <View className='section-card empty-state'>
      <Text className='card-title'>{title}</Text>
      <Text className='muted'>{description}</Text>
      {action ? <View className='empty-state__action'>{action}</View> : null}
    </View>
  )
}
