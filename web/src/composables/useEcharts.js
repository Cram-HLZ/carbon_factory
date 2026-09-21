// composables/useEcharts.js —— 图表初始化 / 自适应 / 销毁的复用封装
// 用法：const { setOption } = useEcharts(elRef) 其中 elRef 为 <div ref="elRef"> 的模板引用
import { onMounted, onBeforeUnmount, shallowRef } from 'vue'
import * as echarts from 'echarts'

export function useEcharts(elRef) {
  const chart = shallowRef(null)

  function resize() {
    if (chart.value) chart.value.resize()
  }

  onMounted(() => {
    if (elRef && elRef.value) chart.value = echarts.init(elRef.value)
    window.addEventListener('resize', resize)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', resize)
    if (chart.value) {
      chart.value.dispose()
      chart.value = null
    }
  })

  function setOption(opt) {
    if (chart.value) chart.value.setOption(opt, true)
  }

  return { setOption }
}