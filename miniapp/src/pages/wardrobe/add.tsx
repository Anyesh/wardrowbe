import React from 'react'
import Taro from '@tarojs/taro'
import { Button, Image, Input, Picker, Text, View } from '@tarojs/components'
import './add.scss'
import PageHeader from '../../components/PageHeader'
import BottomActionBar from '../../components/BottomActionBar'
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
    <View className='page page--with-footer stack wardrobe-add'>
      <PageHeader title='添加单品' subtitle='先拍照或选图，再补充信息。' />

      <View className='section-card stack add-page__preview'>
        <View className='row'>
          <Text className='section-title'>单品照片</Text>
          <Button className={filePath ? 'secondary-button' : 'primary-button'} onClick={chooseImage}>
            {filePath ? '更换照片' : '选择照片'}
          </Button>
        </View>
        {filePath ? (
          <Image className='add-page__preview-image' src={filePath} mode='aspectFill' />
        ) : (
          <Text className='muted'>建议在自然光下拍摄，尽量保持背景干净。</Text>
        )}
      </View>

      <View className='section-card stack'>
        <Text className='section-title'>基础信息</Text>
        <Picker
          mode='selector'
          range={CLOTHING_TYPES.map((item) => item.label)}
          value={typeIndex}
          onChange={(event) => setTypeIndex(Number(event.detail.value))}
        >
          <View className='input'>
            <Text>{CLOTHING_TYPES[typeIndex]?.label || '选择类型'}</Text>
          </View>
        </Picker>
        <Picker
          mode='selector'
          range={CLOTHING_COLORS.map((item) => item.name)}
          value={colorIndex}
          onChange={(event) => setColorIndex(Number(event.detail.value))}
        >
          <View className='input'>
            <Text>{CLOTHING_COLORS[colorIndex]?.name || '选择颜色'}</Text>
          </View>
        </Picker>
        <Input className='input' value={name} placeholder='名称（可选）' onInput={(event) => setName(event.detail.value)} />
      </View>

      <View className='section-card stack'>
        <Text className='section-title'>更多信息（可选）</Text>
        <Input className='input' value={brand} placeholder='品牌（可选）' onInput={(event) => setBrand(event.detail.value)} />
      </View>

      <BottomActionBar>
        <Button className='primary-button' loading={uploading} disabled={uploading} onClick={submit}>
          {filePath ? '上传到衣橱' : '先选择照片'}
        </Button>
      </BottomActionBar>
    </View>
  )
}
