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
      Taro.showToast({ title: '请先选择图片', icon: 'none' })
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
      Taro.showToast({ title: '上传成功', icon: 'success' })
      setTimeout(() => {
        Taro.switchTab({ url: '/pages/wardrobe/index' })
      }, 300)
    } catch (error) {
      Taro.showToast({ title: error instanceof Error ? error.message : '上传失败', icon: 'none' })
    } finally {
      setUploading(false)
    }
  }

  return (
    <View className='page stack'>
      <View className='card stack'>
        <Text className='section-title'>添加到衣橱</Text>
        <Button onClick={chooseImage}>选择拍照或相册</Button>
        {filePath ? <Image className='detail-image' src={filePath} mode='aspectFit' /> : <Text className='muted'>选择一张照片进行预览并上传。</Text>}
        <Picker mode='selector' range={CLOTHING_TYPES.map((item) => item.label)} value={typeIndex} onChange={(event) => setTypeIndex(Number(event.detail.value))}>
          <View className='input'><Text>{CLOTHING_TYPES[typeIndex]?.label || 'Type'}</Text></View>
        </Picker>
        <Picker mode='selector' range={CLOTHING_COLORS.map((item) => item.name)} value={colorIndex} onChange={(event) => setColorIndex(Number(event.detail.value))}>
          <View className='input'><Text>{CLOTHING_COLORS[colorIndex]?.name || 'Color'}</Text></View>
        </Picker>
        <Input className='input' value={name} placeholder='单品名称（可选）' onInput={(event) => setName(event.detail.value)} />
        <Input className='input' value={brand} placeholder='品牌（可选）' onInput={(event) => setBrand(event.detail.value)} />
        <Button loading={uploading} onClick={submit}>上传单品</Button>
      </View>
    </View>
  )
}
