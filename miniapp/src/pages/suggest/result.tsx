import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import './result.scss'
import OutfitCard from '../../components/OutfitCard'
import { acceptOutfit, getOutfit, rejectOutfit, suggestOutfit } from '../../services/outfits'
import { getLastSuggestionId, setLastSuggestionId } from '../../services/session'
import type { Outfit } from '../../shared/types'

export default function SuggestResultPage() {
  const routerId = Taro.getCurrentInstance().router?.params?.id || ''
  const outfitId = routerId || getLastSuggestionId()
  const [outfit, setOutfit] = React.useState<Outfit | null>(null)
  const [loading, setLoading] = React.useState(false)

  const load = React.useCallback(async () => {
    if (!outfitId) return
    const nextOutfit = await getOutfit(outfitId)
    setOutfit(nextOutfit)
  }, [outfitId])

  useDidShow(() => {
    load().catch((error) => Taro.showToast({ title: error instanceof Error ? error.message : '加载失败', icon: 'none' }))
  })

  if (!outfit) {
    return <View className='page'><View className='card'><Text>正在加载建议…</Text></View></View>
  }

  return (
    <View className='page stack'>
      <OutfitCard outfit={outfit} />
      {outfit.highlights?.length ? (
        <View className='card stack'>
          <Text className='section-title'>亮点</Text>
          {outfit.highlights.map((highlight) => <Text key={highlight}>• {highlight}</Text>)}
        </View>
      ) : null}
      {outfit.style_notes ? <View className='card'><Text>{outfit.style_notes}</Text></View> : null}
      <View className='row-wrap'>
        <Button loading={loading} onClick={async () => {
          setLoading(true)
          try {
            const next = await acceptOutfit(outfit.id)
            setOutfit(next)
            Taro.showToast({ title: '已接受', icon: 'success' })
          } finally {
            setLoading(false)
          }
        }}>很喜欢</Button>
        <Button className='button-secondary' loading={loading} onClick={async () => {
          setLoading(true)
          try {
            const next = await rejectOutfit(outfit.id)
            setOutfit(next)
            Taro.showToast({ title: '已拒绝', icon: 'none' })
          } finally {
            setLoading(false)
          }
        }}>拒绝</Button>
        <Button className='button-secondary' loading={loading} onClick={async () => {
          setLoading(true)
          try {
            const next = await suggestOutfit({ occasion: outfit.occasion })
            setLastSuggestionId(next.id)
            setOutfit(next)
          } finally {
            setLoading(false)
          }
        }}>换一套</Button>
      </View>
    </View>
  )
}
