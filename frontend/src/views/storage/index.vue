<template>
  <section class="page" data-module="storage">
    <header class="page-head">
      <div>
        <h2>堆存计费管理</h2>
        <p class="page-desc">按箱号与计费周期唯一计费；金额、堆存天数随周期与堆存记录统一核算，结清后锁定不可改。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记计费单</button>
        <button class="btn" type="button" @click="exportRows">导出对账单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>计费单号</span>
        <input v-model="filters.keyword" placeholder="按计费单号检索" />
      </label>
      <label class="filter-item">
        <span>关联箱号</span>
        <input v-model="filters.container" placeholder="按箱号精确检索" />
      </label>
      <label class="filter-item">
        <span>计费状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <template v-if="row['已结清']">
              <span class="locked-tag">已结清</span>
            </template>
            <template v-else>
              <button class="link" type="button" @click="editRow(row)">修改</button>
              <button class="link" type="button" @click="runAction(nextAction(row.status), row)">
                {{ nextAction(row.status) }}
              </button>
            </template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无堆存计费数据，可先登记计费单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条堆存计费记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/storage'
const columns = ["计费单号", "关联箱号", "计费周期", "堆存天数", "计费标准", "应收金额", "客户名称", "计费状态"]
const statuses = ["待核算", "已核算", "已对账", "已开票"]
const nextActionByStatus: Record<string, string> = {
  "待核算": "生成账单",
  "已核算": "确认对账",
  "已对账": "开具发票",
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({ keyword: '', container: '', status: '' })
const stats = ref<{ label: string; value: number | string }[]>([
  { label: "待核算计费单", value: 0 },
  { label: "应收金额合计（元）", value: 0 },
  { label: "已结清金额（元）", value: 0 },
])

function nextAction(status: string | number | boolean | null): string {
  return nextActionByStatus[String(status)] ?? ''
}

function buildQuery(): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value) params.set(key, value)
  }
  return params.toString()
}

function resetFilters() {
  filters.value = { keyword: '', container: '', status: '' }
  void reload()
}

function exportRows() {
  // 导出与列表使用同一接口的同一过滤口径，保证数字一致。
  window.open(`${ENDPOINT}/export?${buildQuery()}`, '_blank')
}

function openCreate() {
  errorMessage.value = '计费单登记入口尚未接入审批流'
}

async function editRow(row: Row) {
  errorMessage.value = ''
  const period = window.prompt('修改计费周期（如 2026-09-01~2026-09-10 或 2026-09）', String(row['计费周期'] ?? ''))
  if (period === null) return
  const standard = window.prompt('修改计费标准（日费率，如 10 元/天）', String(row['计费标准'] ?? ''))
  if (standard === null) return
  try {
    const response = await request(`${ENDPOINT}/${row.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ values: { 计费周期: period, 计费标准: standard } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '计费单未更新')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '计费单更新失败'
  }
}

async function runAction(action: string, row: Row) {
  if (!action) return
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '堆存计费动作未生效')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存计费操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery()}`)
    if (!response.ok) {
      throw new Error('计费单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await loadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存计费列表读取失败'
  }
}

async function loadStats() {
  // 统计取全量（同一数据口径），不受当前页限制。
  const response = await request(`${ENDPOINT}?size=200`)
  if (!response.ok) return
  const payload = await response.json()
  const all = (payload.items ?? []) as Row[]
  const amountOf = (list: Row[]) => list.reduce((sum, item) => sum + Number(item['应收金额'] || 0), 0)
  stats.value = [
    { label: "待核算计费单", value: all.filter((item) => item.status === '待核算').length },
    { label: "应收金额合计（元）", value: amountOf(all).toFixed(2) },
    { label: "已结清金额（元）", value: amountOf(all.filter((item) => item['已结清'])).toFixed(2) },
  ]
}

onMounted(reload)
</script>
