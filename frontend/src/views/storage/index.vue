<template>
  <section class="page" data-module="storage">
    <header class="page-head">
      <div>
        <h2>堆存计费管理</h2>
        <p class="page-desc">计费单与对账单共用同一份数据；金额和堆存天数按箱号、计费周期统一计算，结清后锁定。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记计费单</button>
        <button class="btn" type="button" @click="exportRows">导出堆存计费清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
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
            <button
              class="link"
              type="button"
              :disabled="isLocked(row)"
              @click="openEdit(row)"
            >
              修改
            </button>
            <button
              v-if="actionFor(row)"
              class="link"
              type="button"
              @click="runAction(String(actionFor(row)), row)"
            >
              {{ actionFor(row) }}
            </button>
            <span v-else class="locked-text">已结清</span>
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

    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <form class="modal-panel" @submit.prevent="saveEntry">
        <h3>{{ editingId === null ? '登记计费单' : '修改计费单' }}</h3>
        <label v-for="field in formFields" :key="field" class="form-item">
          <span>{{ field }}</span>
          <input
            v-model="formValues[field]"
            :disabled="field === '计费单号' && editingId !== null"
            :placeholder="fieldPlaceholder[field]"
          />
        </label>
        <p class="form-tip">保存后系统会按箱号与计费周期重新核算堆存天数和应收金额。</p>
        <div class="form-actions">
          <button class="btn ghost" type="button" @click="closeForm">取消</button>
          <button class="btn primary" type="submit">保存</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type FormValues = Record<string, string>

const ENDPOINT = '/api/storage'
const columns = ["计费单号", "关联箱号", "计费周期", "堆存天数", "计费标准", "应收金额", "客户名称", "计费状态"]
const nextActionMap: Record<string, string> = {
  待核算: '生成账单',
  已核算: '确认对账',
  已对账: '开具发票',
}
const formFields = ["计费单号", "关联箱号", "计费周期", "计费标准", "客户名称"]
const fieldPlaceholder: FormValues = {
  计费单号: '例如 STOR-0004',
  关联箱号: '例如 CSLU1234567',
  计费周期: '例如 2026-09-01 至 2026-09-10',
  计费标准: '例如 10 元/天',
  客户名称: '客户名称',
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = reactive<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const formVisible = ref(false)
const editingId = ref<number | null>(null)
const formValues = reactive<FormValues>({
  计费单号: '',
  关联箱号: '',
  计费周期: '',
  计费标准: '10 元/天',
  客户名称: '',
})

const stats = computed(() => {
  const pending = rows.value.filter(row => !isLocked(row) && row.status !== '已核算').length
  const totalAmount = sumAmount(row => !isLocked(row))
  const invoicedAmount = sumAmount(row => isLocked(row))
  return [
    { label: '当前未结清单', value: pending },
    { label: '当前应收金额', value: totalAmount.toFixed(2) },
    { label: '已结清金额', value: invoicedAmount.toFixed(2) },
  ]
})

function sumAmount(predicate: (row: Row) => boolean): number {
  return rows.value
    .filter(predicate)
    .reduce((sum, row) => sum + Number(row.应收金额 ?? 0), 0)
}

function isLocked(row: Row): boolean {
  return ['已对账', '已开票', '已结清'].includes(String(row.status ?? row.计费状态 ?? ''))
}

function actionFor(row: Row): string | undefined {
  return nextActionMap[String(row.status ?? row.计费状态 ?? '')]
}

function resetFilters() {
  Object.keys(filters).forEach(key => delete filters[key])
  void reload()
}

function exportRows() {
  const query = new URLSearchParams(filters).toString()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function resetForm() {
  formValues.计费单号 = ''
  formValues.关联箱号 = ''
  formValues.计费周期 = ''
  formValues.计费标准 = '10 元/天'
  formValues.客户名称 = ''
  editingId.value = null
}

function openCreate() {
  resetForm()
  errorMessage.value = ''
  formVisible.value = true
}

function openEdit(row: Row) {
  if (isLocked(row)) return
  resetForm()
  editingId.value = Number(row.id)
  formFields.forEach(field => {
    formValues[field] = String(row[field] ?? (field === '计费标准' ? '10 元/天' : ''))
  })
  errorMessage.value = ''
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
  resetForm()
}

async function saveEntry() {
  errorMessage.value = ''
  const url = editingId.value === null ? ENDPOINT : `${ENDPOINT}/${editingId.value}`
  const method = editingId.value === null ? 'POST' : 'PATCH'
  try {
    const response = await request(url, {
      method,
      body: JSON.stringify({ values: { ...formValues } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message || '计费单保存失败')
    }
    closeForm()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '计费单保存失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message || '堆存计费动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存计费操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('计费单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存计费列表读取失败'
  }
}

onMounted(reload)
</script>
