<script setup lang="ts">
import { onMounted } from "vue";

/**
 * 小窝聊天在 UC 里不再用 iframe 内嵌（内嵌会带出 UC 侧边栏、也压窄聊天区），
 * 进来直接整页跳转到 /chat/ 独立页面。
 */
onMounted(() => {
  window.location.replace("/chat/");
});
</script>

<template>
  <div class="chat-view">
    <div class="chat-jump">正在打开小窝聊天…</div>
  </div>
</template>

<style scoped>
.chat-view {
  height: calc(100vh - 64px);
  margin: -16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fafafa;
}
.chat-jump {
  font-size: 14px;
  color: #8c8c8c;
}
</style>
