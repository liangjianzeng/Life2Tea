<template>
  <div ref="chartRef" class="line-chart"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from "vue";
import * as echarts from "echarts";

const props = withDefaults(defineProps<{
  data: any[];
  unit?: string;
  maxValue?: number;
}>(), {
  unit: "",
  maxValue: undefined,
});

const chartRef = ref<HTMLElement | null>(null);
let chartInstance: echarts.ECharts | null = null;

function initChart() {
  if (!chartRef.value) return;

  chartInstance = echarts.init(chartRef.value);

  const hasGpu = props.data.some((d: any) => d.gpu?.utilization != null && d.gpu?.utilization !== undefined);

  const series: any[] = [];

  // CPU
  series.push({
    name: "CPU",
    type: "line",
    data: props.data.map((d: any) => d.cpu),
    smooth: true,
    symbol: "none",
    lineStyle: { width: 2 },
    itemStyle: { color: "#818cf8" },
    areaStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: "rgba(129, 140, 248, 0.3)" },
        { offset: 1, color: "rgba(129, 140, 248, 0.02)" },
      ]),
    },
  });

  // Memory %
  const memPercents = props.data.map((d: any) => {
    if (d.memory && d.memory.total) {
      return Math.round((d.memory.used / d.memory.total) * 100);
    }
    return null;
  });

  series.push({
    name: "Memory",
    type: "line",
    data: memPercents,
    smooth: true,
    symbol: "none",
    lineStyle: { width: 2 },
    itemStyle: { color: "#34d399" },
    areaStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: "rgba(52, 211, 153, 0.25)" },
        { offset: 1, color: "rgba(52, 211, 153, 0.02)" },
      ]),
    },
  });

  // GPU if available
  if (hasGpu) {
    const gpuPercents = props.data.map((d: any) => d.gpu ? d.gpu.utilization : null);
    series.push({
      name: "GPU",
      type: "line",
      data: gpuPercents,
      smooth: true,
      symbol: "none",
      lineStyle: { width: 2 },
      itemStyle: { color: "#fbbf24" },
    });
  }

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: "axis",
      backgroundColor: "#1a1a2e",
      borderColor: "#2d2d4a",
      textStyle: { color: "#e0e0ff", fontSize: 12 },
    },
    legend: {
      data: series.map((s) => s.name),
      top: 0,
      right: 0,
      textStyle: { color: "#888", fontSize: 11 },
      itemWidth: 12,
      itemHeight: 8,
    },
    grid: {
      left: 40,
      right: 16,
      top: 32,
      bottom: 30,
    },
    xAxis: {
      type: "category",
      data: props.data.map((d: any) => {
        const dt = d.timestamp ? new Date(d.timestamp) : null;
        return dt ? dt.toLocaleTimeString() : "";
      }),
      axisLine: { lineStyle: { color: "#2d2d4a" } },
      axisLabel: { color: "#666", fontSize: 10 },
      boundaryGap: false,
    },
    yAxis: {
      type: "value",
      max: props.maxValue || 100,
      axisLine: { show: false },
      axisLabel: { color: "#666", fontSize: 10 },
      splitLine: { lineStyle: { color: "#1a1a2e" } },
    },
    series,
  };

  chartInstance.setOption(option);
}

function resizeChart() {
  chartInstance?.resize();
}

onMounted(async () => {
  await nextTick();
  initChart();
  window.addEventListener("resize", resizeChart);
});

onUnmounted(() => {
  window.removeEventListener("resize", resizeChart);
  chartInstance?.dispose();
});

watch(() => props.data, () => {
  initChart();
}, { deep: true });
</script>

<style scoped>
.line-chart {
  width: 100%;
  height: 280px;
}
</style>
