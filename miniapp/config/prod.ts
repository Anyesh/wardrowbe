export default {
  defineConstants: {
    'process.env.TARO_APP_API_BASE_URL': JSON.stringify(process.env.TARO_APP_API_BASE_URL || ''),
    'process.env.TARO_APP_CLOUDBASE_ENV_ID': JSON.stringify(process.env.TARO_APP_CLOUDBASE_ENV_ID || ''),
    'process.env.TARO_APP_CLOUDBASE_SERVICE': JSON.stringify(process.env.TARO_APP_CLOUDBASE_SERVICE || ''),
  },
}
