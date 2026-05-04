const taroWebPort = Number(process.env.TARO_WEB_PORT || 10086)

export default {
  defineConstants: {
    'process.env.TARO_APP_API_BASE_URL': JSON.stringify(process.env.TARO_APP_API_BASE_URL || 'http://localhost:8000'),
    'process.env.TARO_APP_CLOUDBASE_ENV_ID': JSON.stringify(process.env.TARO_APP_CLOUDBASE_ENV_ID || ''),
    'process.env.TARO_APP_CLOUDBASE_SERVICE': JSON.stringify(process.env.TARO_APP_CLOUDBASE_SERVICE || ''),
  },
  h5: {
    devServer: {
      host: '0.0.0.0',
      port: taroWebPort,
    },
  },
}
