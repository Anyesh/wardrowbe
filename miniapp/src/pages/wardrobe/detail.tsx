import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Image, Input, Text, Textarea, View } from '@tarojs/components'
import './detail.scss'
import PageHeader from '../../components/PageHeader'
import BottomActionBar from '../../components/BottomActionBar'
import { deleteItem, getItem, logWash, logWear, updateItem } from '../../services/items'
import type { Item } from '../../shared/types'
import { joinList, titleCase } from '../../shared/format'

export default function WardrobeDetailPage() {
  const itemId = Taro.getCurrentInstance().router?.params?.id || ''
  const [item, setItem] = React.useState<Item | null>(null)
  const [saving, setSaving] = React.useState(false)

  const load = React.useCallback(async () => {
    if (!itemId) return
    const nextItem = await getItem(itemId)
    setItem(nextItem)
  }, [itemId])

  useDidShow(() => {
    load().catch((error) => Taro.showToast({ title: error instanceof Error ? error.message : '加载失败', icon: 'none' }))
  })

  if (!item) {
    return <View className='page'><View className='card'><Text>正在加载单品…</Text></View></View>
  }

  const save = async () => {
    setSaving(true)
    try {
      const nextItem = await updateItem(itemId, {
        name: item.name,
        brand: item.brand,
        notes: item.notes,
        favorite: item.favorite,
      })
      setItem(nextItem)
      Taro.showToast({ title: '已保存', icon: 'success' })
    } catch (error) {
      Taro.showToast({ title: error instanceof Error ? error.message : '保存失败', icon: 'none' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <View className='page page--with-footer stack wardrobe-detail'>
      <PageHeader title='单品详情' subtitle='先检查状态，再编辑信息。' />

      <View className='detail-hero'>
        <Image
          className='detail-hero__image'
          src={item.image_url || item.medium_url || item.thumbnail_url || item.image_path}
          mode='aspectFill'
        />
      </View>

      <View className='section-card stack wardrobe-detail__summary'>
        <View className='stack wardrobe-detail__summary-main'>
          <Text className='hero-title'>{item.name || titleCase(item.type)}</Text>
          <Text className='muted'>
            {joinList([titleCase(item.type), item.primary_color ? titleCase(item.primary_color) : undefined, item.brand ? titleCase(item.brand) : undefined])}
          </Text>
        </View>
        <View className='row-wrap wardrobe-detail__badges'>
          <Text className={`badge ${item.status === 'ready' ? 'badge--ok' : ''}`}>{titleCase(item.status)}</Text>
          {item.needs_wash ? <Text className='badge badge--warn'>需要清洗</Text> : null}
          {item.favorite ? <Text className='badge'>已收藏</Text> : null}
        </View>
      </View>

      <View className='section-card stack wardrobe-detail__edit'>
        <Text className='section-title'>编辑信息</Text>
        <Input className='input' value={item.name || ''} placeholder='名称' onInput={(event) => setItem({ ...item, name: event.detail.value })} />
        <Input className='input' value={item.brand || ''} placeholder='品牌' onInput={(event) => setItem({ ...item, brand: event.detail.value })} />
        <Textarea className='textarea' value={item.notes || ''} placeholder='备注' onInput={(event) => setItem({ ...item, notes: event.detail.value })} />
      </View>

      <View className='section-card stack detail-actions'>
        <Text className='section-title'>快捷操作</Text>
        <View className='row-wrap'>
          <Button
            className={item.favorite ? 'secondary-button' : 'primary-button'}
            onClick={() => setItem({ ...item, favorite: !item.favorite })}
          >
            {item.favorite ? '取消收藏' : '收藏'}
          </Button>
          <Button
            className='secondary-button'
            onClick={async () => {
              const next = await logWear(itemId)
              setItem(next)
            }}
          >
            记录穿着
          </Button>
          <Button
            className='secondary-button'
            onClick={async () => {
              const next = await logWash(itemId)
              setItem(next)
            }}
          >
            标记已洗
          </Button>
        </View>
      </View>

      <View className='section-card stack wardrobe-detail__danger'>
        <Text className='section-title'>危险操作</Text>
        <Text className='muted'>删除后无法恢复，请谨慎操作。</Text>
        <Button
          className='wardrobe-detail__danger-button'
          onClick={async () => {
            const result = await Taro.showModal({ title: '删除单品', content: '确定要从衣橱中删除这件单品吗？' })
            if (result.confirm) {
              await deleteItem(itemId)
              Taro.navigateBack()
            }
          }}
        >
          删除单品
        </Button>
      </View>

      <BottomActionBar>
        <Button className='primary-button' loading={saving} disabled={saving} onClick={save}>
          保存修改
        </Button>
      </BottomActionBar>
    </View>
  )
}
