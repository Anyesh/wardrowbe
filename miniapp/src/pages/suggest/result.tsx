import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import './result.scss'
import PageHeader from '../../components/PageHeader'
import BottomActionBar from '../../components/BottomActionBar'
import EmptyState from '../../components/EmptyState'
import OutfitCard from '../../components/OutfitCard'
import { acceptOutfit, getOutfit, rejectOutfit, suggestOutfit } from '../../services/outfits'
import { getLastSuggestionId, setLastSuggestionId } from '../../services/session'
import type { Outfit } from '../../shared/types'

export default function SuggestResultPage() {
  const routerId = Taro.getCurrentInstance().router?.params?.id || ''
  const outfitId = routerId || getLastSuggestionId()
  const [outfit, setOutfit] = React.useState<Outfit | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState('')

  const load = React.useCallback(async () => {
    if (!outfitId) {
      setError('还没有可查看的穿搭建议，先去生成一套吧。')
      return
    }

    setError('')
    const nextOutfit = await getOutfit(outfitId)
    setOutfit(nextOutfit)
  }, [outfitId])

  useDidShow(() => {
    load().catch((loadError) => {
      setError(loadError instanceof Error ? loadError.message : '加载失败')
      Taro.showToast({ title: loadError instanceof Error ? loadError.message : '加载失败', icon: 'none' })
    })
  })

  const reroll = async () => {
    if (!outfit) return
    setLoading(true)
    try {
      const next = await suggestOutfit({ occasion: outfit.occasion })
      setLastSuggestionId(next.id)
      setOutfit(next)
      setError('')
    } catch (actionError) {
      Taro.showToast({ title: actionError instanceof Error ? actionError.message : '换一套失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const accept = async () => {
    if (!outfit) return
    setLoading(true)
    try {
      const next = await acceptOutfit(outfit.id)
      setOutfit(next)
      Taro.showToast({ title: '已接受', icon: 'success' })
    } catch (actionError) {
      Taro.showToast({ title: actionError instanceof Error ? actionError.message : '操作失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const reject = async () => {
    if (!outfit) return
    setLoading(true)
    try {
      const next = await rejectOutfit(outfit.id)
      setOutfit(next)
      Taro.showToast({ title: '已拒绝', icon: 'none' })
    } catch (actionError) {
      Taro.showToast({ title: actionError instanceof Error ? actionError.message : '操作失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  if (!outfit) {
    return (
      <View className='page stack'>
        <PageHeader title='穿搭结果' subtitle='查看推荐结论与下一步操作。' />
        <EmptyState
          title='还没有穿搭结果'
          description={error || '先去“穿搭建议”生成一套新的穿搭。'}
          action={(
            <Button className='primary-button' onClick={() => Taro.switchTab({ url: '/pages/suggest/index' })}>
              去生成穿搭
            </Button>
          )}
        />
      </View>
    )
  }

  return (
    <View className='page page--with-footer stack result-page'>
      <PageHeader title='穿搭结果' subtitle='先看结论，再决定是否接受这套穿搭。' />

      <OutfitCard outfit={outfit} />

      {outfit.highlights?.length ? (
        <View className='section-card stack result-page__highlights'>
          <Text className='section-title'>推荐亮点</Text>
          {outfit.highlights.map((highlight) => (
            <Text key={highlight} className='muted'>
              • {highlight}
            </Text>
          ))}
        </View>
      ) : null}

      {outfit.style_notes ? (
        <View className='section-card stack result-page__notes'>
          <Text className='section-title'>搭配说明</Text>
          <Text className='muted'>{outfit.style_notes}</Text>
        </View>
      ) : null}

      <BottomActionBar>
        <Button className='primary-button' loading={loading} disabled={loading} onClick={accept}>
          很喜欢，接受这套
        </Button>
        <View className='row result-page__secondary-actions'>
          <Button className='secondary-button result-page__secondary-button' loading={loading} disabled={loading} onClick={reroll}>
            换一套
          </Button>
          <Button className='secondary-button result-page__secondary-button' loading={loading} disabled={loading} onClick={reject}>
            拒绝
          </Button>
        </View>
      </BottomActionBar>
    </View>
  )
}
