import { definePlugin } from "@halo-dev/ui-shared";
import ChatView from "./views/ChatView.vue";

export default definePlugin({
  components: {},
  routes: [],
  ucRoutes: [
    {
      parentName: "Root",
      route: {
        path: "/chat",
        name: "SamHouseChat",
        component: ChatView,
        meta: {
          title: "小窝聊天",
          searchable: false,
          menu: {
            name: "小窝聊天",
            priority: 40,
          },
        },
      },
    },
  ],
  extensionPoints: {},
});
