import React from 'react'
import { Text, View } from '@tarojs/components'

interface PageHeaderProps {
  eyebrow?: string
  title: string
  subtitle?: string
  rightSlot?: React.ReactNode
}

export default function PageHeader({ eyebrow, title, subtitle, rightSlot }: PageHeaderProps) {
  return (
    <View className='page-header'>
      <View className='row page-header__row'>
        <View className='stack page-header__content'>
          {eyebrow ? <Text className='page-header__eyebrow'>{eyebrow}</Text> : null}
          <Text className='page-header__title'>{title}</Text>
          {subtitle ? <Text className='page-header__subtitle'>{subtitle}</Text> : null}
        </View>
        {rightSlot ? <View className='page-header__right'>{rightSlot}</View> : null}
      </View>
    </View>
  )
}
