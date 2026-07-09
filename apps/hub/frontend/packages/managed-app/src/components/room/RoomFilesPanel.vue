<template>
  <div class="room-panel-body">
    <form class="file-form" @submit.prevent="handleUploadFile">
      <div class="file-form-row">
        <select id="room-file-purpose" v-model="selectedFilePurpose" :disabled="uploadingFile" :aria-label="t('room_files_purpose_label')">
          <option value="artifact">{{ t('room_files_purpose_artifact') }}</option>
          <option value="instruction">{{ t('room_files_purpose_instruction') }}</option>
        </select>
        <input
          id="room-file"
          type="file"
          :disabled="uploadingFile"
          :aria-label="t('room_files_upload_label')"
          @change="handleFileSelected"
        />
        <button class="primary-button" type="submit" :disabled="uploadingFile || !selectedFile">
          <span v-if="uploadingFile" class="spinner" aria-hidden="true"></span>
          <RoomIcon v-else name="upload" :size="14" />
          {{ t('room_files_upload') }}
        </button>
      </div>
      <p class="panel-note">
        {{ t('room_files_limit').replace('{size}', formatBytes(maxFileBytes)) }}
        ·
        {{
          t('room_files_quota')
            .replace('{remainingFiles}', String(remainingFiles))
            .replace('{maxFiles}', String(maxFiles))
            .replace('{remainingBytes}', formatBytes(remainingBytes))
            .replace('{maxBytes}', formatBytes(maxTotalBytes))
        }}
      </p>
    </form>

    <div v-if="loading" class="panel-note">{{ t('loading') }}</div>

    <div v-else-if="files.length === 0" class="empty-note">
      <p class="empty-title">{{ t('room_files_empty') }}</p>
      <p class="empty-body">{{ t('room_files_empty_body') }}</p>
    </div>

    <div v-else class="room-files">
      <article v-for="file in files" :key="file.file_id" class="room-file">
        <RoomIcon name="folder" :size="18" />
        <div class="room-file-main">
          <span class="room-file-name">{{ file.filename }}</span>
          <span class="file-meta">
            <span class="file-purpose">{{ t(file.purpose === 'instruction' ? 'room_files_purpose_instruction' : 'room_files_purpose_artifact') }}</span>
            {{ formatBytes(file.size_bytes) }} · {{ relativeTime(file.created_at) }} ·
            {{ t('room_files_uploaded_by').replace('{name}', file.uploaded_by_name) }}
          </span>
        </div>
        <span class="file-actions">
          <a
            class="icon-button"
            :href="fileDownloadHref(file.file_id)"
            download
            :aria-label="t('room_files_download')"
            :title="t('room_files_download')"
          >
            <RoomIcon name="download" :size="14" />
          </a>
          <button
            class="icon-button danger"
            type="button"
            :aria-label="t('confirm_delete_btn')"
            :title="t('confirm_delete_btn')"
            :disabled="mutatingFileId === file.file_id"
            @click="deleteFile(file)"
          >
            <RoomIcon name="trash" :size="14" />
          </button>
        </span>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import {
  deleteSessionFile,
  fetchSessionFiles,
  sessionFileDownloadUrl,
  uploadSessionFile,
  type RoomFile,
} from '../../api/managed'
import { getApiErrorMessage } from '../../api/client'
import { useManagedI18n } from '../../i18n'
import { useToast } from '../../composables/useToast'
import { relativeTime } from '../../lib/time'
import RoomIcon from './RoomIcon.vue'

const props = defineProps<{
  slug: string
  sessionId: string
}>()

const emit = defineEmits<{
  count: [value: number]
}>()

const { t } = useManagedI18n()
const toast = useToast()

const loading = ref(true)
const uploadingFile = ref(false)
const mutatingFileId = ref('')
const files = ref<RoomFile[]>([])
const selectedFile = ref<File | null>(null)
const selectedFilePurpose = ref<RoomFile['purpose']>('artifact')
const maxFileBytes = ref(0)
const maxFiles = ref(0)
const maxTotalBytes = ref(0)
const remainingFiles = ref(0)
const remainingBytes = ref(0)

watch(files, value => emit('count', value.length), { deep: false })

async function loadFiles() {
  loading.value = true
  try {
    const fileList = await fetchSessionFiles(props.slug, props.sessionId)
    files.value = fileList.files
    maxFileBytes.value = fileList.max_file_bytes
    maxFiles.value = fileList.max_files
    maxTotalBytes.value = fileList.max_total_bytes
    remainingFiles.value = fileList.remaining_files
    remainingBytes.value = fileList.remaining_bytes
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    loading.value = false
  }
}

function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] || null
}

function fileDownloadHref(fileId: string): string {
  return sessionFileDownloadUrl(props.slug, props.sessionId, fileId)
}

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = value
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size = size / 1024
    unitIndex += 1
  }
  return `${size >= 10 || unitIndex === 0 ? Math.round(size) : size.toFixed(1)} ${units[unitIndex]}`
}

async function handleUploadFile() {
  if (!selectedFile.value) return
  uploadingFile.value = true
  try {
    const result = await uploadSessionFile(props.slug, props.sessionId, selectedFile.value, selectedFilePurpose.value)
    files.value = [...files.value, result.file]
    remainingFiles.value = Math.max(remainingFiles.value - 1, 0)
    remainingBytes.value = Math.max(remainingBytes.value - result.file.size_bytes, 0)
    selectedFile.value = null
    selectedFilePurpose.value = 'artifact'
    const input = document.getElementById('room-file') as HTMLInputElement | null
    if (input) input.value = ''
    toast.show(t('room_files_uploaded'), 'success')
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    uploadingFile.value = false
  }
}

async function deleteFile(file: RoomFile) {
  mutatingFileId.value = file.file_id
  try {
    await deleteSessionFile(props.slug, props.sessionId, file.file_id)
    files.value = files.value.filter(item => item.file_id !== file.file_id)
    remainingFiles.value = Math.min(remainingFiles.value + 1, maxFiles.value)
    remainingBytes.value = Math.min(remainingBytes.value + file.size_bytes, maxTotalBytes.value)
    toast.show(t('room_files_deleted'), 'success')
  } catch (err) {
    toast.show(getApiErrorMessage(err), 'error')
  } finally {
    mutatingFileId.value = ''
  }
}

onMounted(loadFiles)
</script>

<style scoped>
.room-panel-body { display: flex; flex-direction: column; gap: 14px; }
.file-form { display: flex; flex-direction: column; gap: 8px; }
.file-form-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
select {
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--soft);
  color: var(--ink);
  font-size: 0.88rem;
}
select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); outline: none; }
input[type='file'] { color: var(--muted); font-size: 0.84rem; flex: 1; min-width: 200px; }
input[type='file']::file-selector-button {
  padding: 9px 14px;
  margin-right: 10px;
  background: var(--card-bg);
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: 10px;
  font-size: 0.82rem;
  cursor: pointer;
  transition: all 0.15s ease;
}
input[type='file']::file-selector-button:hover { border-color: var(--accent); color: var(--accent); }
.panel-note { color: var(--muted); font-size: 0.8rem; margin: 0; }
.empty-note { text-align: center; padding: 18px 12px; }
.empty-title { margin: 0 0 4px; color: var(--ink); font-weight: 600; }
.empty-body { margin: 0; color: var(--muted); font-size: 0.88rem; }
.room-files { display: flex; flex-direction: column; gap: 8px; }
.room-file {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 10px 14px;
  background: var(--card-bg);
  color: var(--muted);
}
.room-file-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.room-file-name { color: var(--ink); font-weight: 600; font-size: 0.92rem; word-break: break-word; }
.file-meta { color: var(--muted); font-size: 0.78rem; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.file-purpose {
  display: inline-flex;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 1px 8px;
  color: var(--accent);
  font-size: 0.68rem;
  font-weight: 700;
}
.file-actions { display: inline-flex; gap: 6px; }
.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  transition: all 0.15s ease;
}
.icon-button:hover { color: var(--ink); border-color: var(--hover-line); }
.icon-button.danger:hover { color: #F0997B; border-color: rgba(240, 153, 123, 0.4); }
.icon-button:disabled { opacity: 0.5; cursor: default; }
@media (max-width: 720px) {
  .file-form-row { flex-direction: column; align-items: stretch; }
}
</style>
