import React from 'react'
import { Text, View } from '@tarojs/components'

interface StatCardProps {
  label: string
  value: string | number
  hint: string
}

export default function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <View className='section-card stat-card'>
      <Text className='section-title'>{label}</Text>
      <Text className='hero-title'>{value}</Text>
      <Text className='muted'>{hint}</Text>
    </View>
  )
}
