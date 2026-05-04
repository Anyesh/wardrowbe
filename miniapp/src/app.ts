import React from 'react'
import Taro from '@tarojs/taro'
import './app.scss'
import { CLOUDBASE_ENV_ID } from './shared/constants'

export default function App({ children }: { children: React.ReactNode }) {
  React.useEffect(() => {
    if (Taro.getEnv() === Taro.ENV_TYPE.WEAPP && CLOUDBASE_ENV_ID) {
      const cloud = (Taro as unknown as { cloud?: { init?: (options: { env: string }) => void } }).cloud
      cloud?.init?.({ env: CLOUDBASE_ENV_ID })
    }
  }, [])

  return children
}
