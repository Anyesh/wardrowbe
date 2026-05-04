const isProd = process.env.NODE_ENV === 'production'

const sharedConstants = {
  'process.env.TARO_APP_CLOUDBASE_ENV_ID': JSON.stringify(process.env.TARO_APP_CLOUDBASE_ENV_ID || ''),
  'process.env.TARO_APP_CLOUDBASE_SERVICE': JSON.stringify(process.env.TARO_APP_CLOUDBASE_SERVICE || ''),
}

export default {
  projectName: 'wardrowbe-miniapp',
  date: '2026-05-04',
  designWidth: 750,
  deviceRatio: {
    640: 2.34 / 2,
    750: 1,
    828: 1.81 / 2,
  },
  sourceRoot: 'src',
  outputRoot: 'dist',
  framework: 'react',
  compiler: 'webpack5',
  plugins: [],
  defineConstants: {
    ...sharedConstants,
    'process.env.TARO_APP_API_BASE_URL': JSON.stringify(process.env.TARO_APP_API_BASE_URL || (isProd ? '' : 'http://localhost:8000')),
  },
  copy: {
    patterns: [],
    options: {},
  },
  mini: {
    postcss: {
      pxtransform: {
        enable: true,
        config: {},
      },
      url: {
        enable: true,
        config: {
          limit: 1024,
        },
      },
      cssModules: {
        enable: false,
        config: {
          namingPattern: 'module',
          generateScopedName: '[name]__[local]___[hash:base64:5]',
        },
      },
    },
  },
}
