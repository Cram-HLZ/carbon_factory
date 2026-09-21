<template>
  <div class="login-wrap">
    <div class="card p-4">
      <div class="text-center mb-3">
        <div class="fs-4 brand">🌿 数字孪生锂电工厂</div>
        <div class="text-secondary small">碳排AI监测系统</div>
      </div>

      <ul class="nav nav-tabs mb-3">
        <li class="nav-item">
          <button class="nav-link" :class="{ active: tab === 'login' }" @click="switchTab('login')">登 录</button>
        </li>
        <li class="nav-item">
          <button class="nav-link" :class="{ active: tab === 'register' }" @click="switchTab('register')">注 册</button>
        </li>
      </ul>

      <!-- 登录 -->
      <div v-show="tab === 'login'">
        <div v-if="loginErr" class="alert alert-danger py-2 small">{{ loginErr }}</div>
        <div class="mb-3">
          <label class="form-label small">账号</label>
          <input v-model.trim="form.account" class="form-control" placeholder="请输入账号" autocomplete="username" @keydown.enter="doLogin" />
        </div>
        <div class="mb-4">
          <label class="form-label small">密码</label>
          <div class="input-group">
            <input v-model="form.password" class="form-control" :type="showLoginPwd ? 'text' : 'password'" placeholder="请输入密码" autocomplete="current-password" @keydown.enter="doLogin" />
            <button class="btn btn-outline-secondary toggle-pwd" type="button" @click="showLoginPwd = !showLoginPwd">{{ showLoginPwd ? '隐藏' : '显示' }}</button>
          </div>
        </div>
        <button class="btn w-100 text-white" style="background:#0f766e" :disabled="logging" @click="doLogin">{{ logging ? '登录中…' : '登 录' }}</button>
        <div class="text-center text-secondary small mt-3">默认账号：admin / manager / operator</div>
      </div>

      <!-- 注册 -->
      <div v-show="tab === 'register'">
        <div v-if="regErr" class="alert alert-danger py-2 small">{{ regErr }}</div>
        <div class="mb-3">
          <label class="form-label small">账号</label>
          <input v-model.trim="reg.account" class="form-control" placeholder="3-64 位，用于登录" autocomplete="username" />
        </div>
        <div class="mb-3">
          <label class="form-label small">密码</label>
          <div class="input-group">
            <input v-model="reg.password" class="form-control" :type="showRegPwd ? 'text' : 'password'" placeholder="至少 6 位" autocomplete="new-password" />
            <button class="btn btn-outline-secondary toggle-pwd" type="button" @click="showRegPwd = !showRegPwd">{{ showRegPwd ? '隐藏' : '显示' }}</button>
          </div>
        </div>
        <div class="mb-4">
          <label class="form-label small">确认密码</label>
          <div class="input-group">
            <input v-model="reg.password2" class="form-control" :type="showRegPwd ? 'text' : 'password'" placeholder="再次输入密码" autocomplete="new-password" @keydown.enter="doRegister" />
            <button class="btn btn-outline-secondary toggle-pwd" type="button" @click="showRegPwd = !showRegPwd">{{ showRegPwd ? '隐藏' : '显示' }}</button>
          </div>
        </div>
        <button class="btn w-100 text-white" style="background:#10b981" :disabled="registering" @click="doRegister">{{ registering ? '注册中…' : '注 册' }}</button>
        <div class="text-secondary small mt-3">注册账号默认为「运维岗」，可查看设备与告警</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const tab = ref('login')
const loginErr = ref('')
const regErr = ref('')
const logging = ref(false)
const registering = ref(false)
const showLoginPwd = ref(false)
const showRegPwd = ref(false)

const form = reactive({ account: '', password: '' })
const reg = reactive({ account: '', password: '', password2: '' })

function switchTab(t) {
  tab.value = t
  loginErr.value = ''
  regErr.value = ''
}

async function doLogin() {
  loginErr.value = ''
  if (!form.account || !form.password) { loginErr.value = '请输入账号和密码'; return }
  logging.value = true
  try {
    await auth.login(form.account, form.password)
    router.push('/overview')
  } catch (e) {
    loginErr.value = errMsg(e) || '登录失败，请检查后端服务'
  } finally {
    logging.value = false
  }
}

async function doRegister() {
  regErr.value = ''
  if (reg.account.length < 3) { regErr.value = '账号至少 3 位'; return }
  if (reg.password.length < 6) { regErr.value = '密码至少 6 位'; return }
  if (reg.password !== reg.password2) { regErr.value = '两次输入的密码不一致'; return }
  registering.value = true
  try {
    await auth.register(reg.account, reg.password)
    router.push('/overview')
  } catch (e) {
    regErr.value = errMsg(e) || '注册失败，请检查后端服务'
  } finally {
    registering.value = false
  }
}

function errMsg(e) {
  const d = e && e.response && e.response.data
  return (d && (d.detail || d.message)) || (e && e.message) || ''
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f766e, #10b981);
}
.card { width: 100%; max-width: 420px; border-radius: 16px; box-shadow: 0 8px 30px rgba(0,0,0,.18); }
.brand { font-weight: 700; color: #0f766e; }
.nav-tabs .nav-link { color: #0f766e; font-weight: 600; }
.toggle-pwd { color: #6b7280; }
</style>