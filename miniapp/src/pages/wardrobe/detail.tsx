import React from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Image, Input, Text, Textarea, View } from '@tarojs/components'
import './detail.scss'
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
    <View className='page stack'>
      <Image className='detail-image' src={item.image_url || item.medium_url || item.thumbnail_url || item.image_path} mode='aspectFit' />
      <View className='card stack'>
        <Text className='section-title'>单品详情</Text>
        <Input className='input' value={item.name || ''} placeholder='名称' onInput={(event) => setItem({ ...item, name: event.detail.value })} />
        <Input className='input' value={item.brand || ''} placeholder='品牌' onInput={(event) => setItem({ ...item, brand: event.detail.value })} />
        <Textarea className='textarea' value={item.notes || ''} placeholder='备注' onInput={(event) => setItem({ ...item, notes: event.detail.value })} />
        <Text className='muted'>{joinList([titleCase(item.type), item.primary_color ? titleCase(item.primary_color) : undefined])}</Text>
        <View className='row-wrap'>
          <Button size='mini' onClick={() => setItem({ ...item, favorite: !item.favorite })}>{item.favorite ? '取消收藏' : '收藏'}</Button>
          <Button size='mini' className='button-secondary' onClick={async () => { const next = await logWash(itemId); setItem(next) }}>标记已洗</Button>
          <Button size='mini' className='button-secondary' onClick={async () => { const next = await logWear(itemId); setItem(next) }}>记录穿着</Button>
        </View>
        <Button loading={saving} onClick={save}>保存修改</Button>
        <Button className='button-secondary' onClick={async () => {
          const result = await Taro.showModal({ title: '删除单品', content: '确定要从衣橱中删除这件单品吗？' })
          if (result.confirm) {
            await deleteItem(itemId)
            Taro.navigateBack()
          }
        }}>删除单品</Button>
      </View>
    </View>
  )
}
