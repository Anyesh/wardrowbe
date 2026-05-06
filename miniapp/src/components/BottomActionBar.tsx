import React from 'react'
import { View } from '@tarojs/components'

export default function BottomActionBar({ children }: { children: React.ReactNode }) {
  return <View className='bottom-action-bar'>{children}</View>
}
