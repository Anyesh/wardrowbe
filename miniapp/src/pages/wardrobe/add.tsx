import React from 'react'
import Taro from '@tarojs/taro'
import { Button, Image, Input, Picker, Text, View } from '@tarojs/components'
import './add.scss'
import { CLOTHING_COLORS, CLOTHING_TYPES } from '../../shared/constants'
import { uploadItem } from '../../services/items'

export default function WardrobeAddPage() {
  const [filePath, setFilePath] = React.useState('')
  const [typeIndex, setTypeIndex] = React.useState(0)
  const [colorIndex, setColorIndex] = React.useState(0)
  const [name, setName] = React.useState('')
  const [brand, setBrand] = React.useState('')
  const [uploading, setUploading] = React.useState(false)

  const chooseImage = async () => {
    const response = await Taro.chooseMedia({ count: 1, mediaType: ['image'], sourceType: ['album', 'camera'] })
    const tempFile = response.tempFiles?.[0]
    if (tempFile?.tempFilePath) {
      setFilePath(tempFile.tempFilePath)
    }
  }

  const submit = async () => {
    if (!filePath) {
      Taro.showToast({ title: 'Choose an image first', icon: 'none' })
      return
    }
    setUploading(true)
    try {
      await uploadItem(filePath, {
        ...(CLOTHING_TYPES[typeIndex] ? { type: CLOTHING_TYPES[typeIndex].value } : {}),
        ...(name ? { name } : {}),
        ...(brand ? { brand } : {}),
        ...(CLOTHING_COLORS[colorIndex] ? { primary_color: CLOTHING_COLORS[colorIndex].value } : {}),
      })
      Taro.showToast({ title: 'Uploaded', icon: 'success' })
      setTimeout(() => {
        Taro.switchTab({ url: '/pages/wardrobe/index' })
      }, 300)
    } catch (error) {
      Taro.showToast({ title: error instanceof Error ? error.message : 'Upload failed', icon: 'none' })
    } finally {
      setUploading(false)
    }
  }

  return (
    <View className='page stack'>
      <View className='card stack'>
        <Text className='section-title'>Add to wardrobe</Text>
        <Button onClick={chooseImage}>Choose camera or gallery</Button>
        {filePath ? <Image className='detail-image' src={filePath} mode='aspectFit' /> : <Text className='muted'>Select a photo to preview and upload it.</Text>}
        <Picker mode='selector' range={CLOTHING_TYPES.map((item) => item.label)} value={typeIndex} onChange={(event) => setTypeIndex(Number(event.detail.value))}>
          <View className='input'><Text>{CLOTHING_TYPES[typeIndex]?.label || 'Type'}</Text></View>
        </Picker>
        <Picker mode='selector' range={CLOTHING_COLORS.map((item) => item.name)} value={colorIndex} onChange={(event) => setColorIndex(Number(event.detail.value))}>
          <View className='input'><Text>{CLOTHING_COLORS[colorIndex]?.name || 'Color'}</Text></View>
        </Picker>
        <Input className='input' value={name} placeholder='Item name (optional)' onInput={(event) => setName(event.detail.value)} />
        <Input className='input' value={brand} placeholder='Brand (optional)' onInput={(event) => setBrand(event.detail.value)} />
        <Button loading={uploading} onClick={submit}>Upload item</Button>
      </View>
    </View>
  )
}
