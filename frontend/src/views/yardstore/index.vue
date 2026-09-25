<template>
  <section class="page" data-module="yardstore">
    <header class="page-head">
      <div>
        <h2>堆存记录管理</h2>
        <p class="page-desc">维护堆存单，堆存天数按开始、结束日期自动计算，并同步刷新未结清计费单。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记堆存单</button>
        <button class="btn" type="button" @click="exportRows">导出堆存记录清单</button>
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
            <button class="link" type="button" @click="openEdit(row)">修改</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无堆存记录数据，可先登记堆存单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条堆存记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <form class="modal-panel" @submit.prevent="saveEntry">
        <h3>{{ editingId === null ? '登记堆存单' : '修改堆存单' }}</h3>
        <label v-for="field in formFields" :key="field" class="form-item">
          <span>{{ field }}</span>
          <input
            v-model="formValues[field]"
            :disabled="field === '堆存单号' && editingId !== null"
            :placeholder="fieldPlaceholder[field]"
          />
        </label>
        <p class="form-tip">保存后会按开始和结束日期重新计算堆存天数，并同步到未结清计费单。</p>
        <div class="form-actions">
          <button class="btn ghost" type="button" @click="closeForm">取消</button>
          <button class="btn primary" type="submit">保存</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type FormValues = Record<string, string>

const ENDPOINT = '/api/yardstore'
const columns = ["堆存单号", "关联箱号", "箱区编号", "贝位号", "堆存开始", "堆存结束", "堆存天数", "堆存状态"]
const actions = ["确认进场", "确认提离", "撤销堆存"]
const formFields = ["堆存单号", "关联箱号", "箱区编号", "贝位号", "堆存开始", "堆存结束"]
const fieldPlaceholder: FormValues = {
  堆存单号: '例如 YARD-0004',
  关联箱号: '例如 CSLU1234567',
  箱区编号: '例如 A-01',
  贝位号: '例如 0101',
  堆存开始: '例如 2026-09-01',
  堆存结束: '例如 2026-09-05',
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = reactive<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const formVisible = ref(false)
const editingId = ref<number | null>(null)
const formValues = reactive<FormValues>({
  堆存单号: '',
  关联箱号: '',
  箱区编号: '',
  贝位号: '',
  堆存开始: '',
  堆存结束: '',
})

const stats = [
  { label: '堆存中箱量', value: 0 },
  { label: '今日进场箱量', value: 0 },
  { label: '今日提离箱量', value: 0 },
]

function resetFilters() {
  Object.keys(filters).forEach(key => delete filters[key])
  void reload()
}

function exportRows() {
  const query = new URLSearchParams(filters).toString()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function resetForm() {
  formFields.forEach(field => { formValues[field] = '' })
  editingId.value = null
}

function openCreate() {
  resetForm()
  errorMessage.value = ''
  formVisible.value = true
}

function openEdit(row: Row) {
  resetForm()
  editingId.value = Number(row.id)
  formFields.forEach(field => {
    formValues[field] = String(row[field] ?? '')
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
      throw new Error(payload.message || '堆存单保存失败')
    }
    closeForm()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存单保存失败'
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
      throw new Error(payload.message || '堆存记录动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存记录操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('堆存单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存记录列表读取失败'
  }
}

onMounted(reload)
</script>
