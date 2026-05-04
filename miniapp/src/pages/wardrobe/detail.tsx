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
    load().catch((error) => Taro.showToast({ title: error instanceof Error ? error.message : 'Load failed', icon: 'none' }))
  })

  if (!item) {
    return <View className='page'><View className='card'><Text>Loading item…</Text></View></View>
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
      Taro.showToast({ title: 'Saved', icon: 'success' })
    } catch (error) {
      Taro.showToast({ title: error instanceof Error ? error.message : 'Save failed', icon: 'none' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <View className='page stack'>
      <Image className='detail-image' src={item.image_url || item.medium_url || item.thumbnail_url || item.image_path} mode='aspectFit' />
      <View className='card stack'>
        <Text className='section-title'>Item details</Text>
        <Input className='input' value={item.name || ''} placeholder='Name' onInput={(event) => setItem({ ...item, name: event.detail.value })} />
        <Input className='input' value={item.brand || ''} placeholder='Brand' onInput={(event) => setItem({ ...item, brand: event.detail.value })} />
        <Textarea className='textarea' value={item.notes || ''} placeholder='Notes' onInput={(event) => setItem({ ...item, notes: event.detail.value })} />
        <Text className='muted'>{joinList([titleCase(item.type), item.primary_color ? titleCase(item.primary_color) : undefined])}</Text>
        <View className='row-wrap'>
          <Button size='mini' onClick={() => setItem({ ...item, favorite: !item.favorite })}>{item.favorite ? 'Unfavorite' : 'Favorite'}</Button>
          <Button size='mini' className='button-secondary' onClick={async () => { const next = await logWash(itemId); setItem(next) }}>Mark washed</Button>
          <Button size='mini' className='button-secondary' onClick={async () => { const next = await logWear(itemId); setItem(next) }}>Log wear</Button>
        </View>
        <Button loading={saving} onClick={save}>Save changes</Button>
        <Button className='button-secondary' onClick={async () => {
          const result = await Taro.showModal({ title: 'Delete item', content: 'Remove this item from your wardrobe?' })
          if (result.confirm) {
            await deleteItem(itemId)
            Taro.navigateBack()
          }
        }}>Delete item</Button>
      </View>
    </View>
  )
}
